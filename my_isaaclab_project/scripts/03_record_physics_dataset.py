#!/usr/bin/env python
"""Thin Isaac Lab entry for S4 scene debug and right-arm reach control."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from isaaclab.app import AppLauncher


parser = argparse.ArgumentParser(description="Run S4 Isaac Lab grasping debug utilities.")
parser.add_argument("--table-top-z", type=float, default=None, help="World Z height for task objects.")
parser.add_argument("--scene-usd", type=Path, default=None, help="Local background scene USD.")
parser.add_argument("--table-usd", type=Path, default=None, help="Local visual table USD.")
parser.add_argument("--table-visual-z", type=float, default=0.0, help="World Z translation for the visual table USD.")
parser.add_argument("--table-scale", type=float, default=1.0, help="Uniform scale for the visual table USD.")
parser.add_argument("--robot-base-z", type=float, default=0.98, help="World Z for fixed robot base_link.")
parser.add_argument("--task-x", type=float, default=0.55, help="World X for block centers.")
parser.add_argument("--task-y", type=float, default=0.0, help="World Y center for table and task objects.")
parser.add_argument("--block-y-offset", type=float, default=0.20, help="Half spacing between red and blue blocks.")
parser.add_argument("--plate-x", type=float, default=0.55, help="World X for plate center.")
parser.add_argument("--continuous", action="store_true", help="Run forever for debug.")
parser.add_argument("--keyboard-jog", action="store_true", help="Enable live keyboard joint jogging.")
parser.add_argument("--jog-step", type=float, default=0.03, help="Joint increment for keyboard jogging, in radians.")
parser.add_argument("--control-file", type=Path, default=Path("/tmp/s4_joint_command.json"))
parser.add_argument("--arm-control-file", type=Path, default=Path("/tmp/s4_arm_control.json"))
parser.add_argument("--print-layout", action="store_true")
parser.add_argument("--joint-stiffness", type=float, default=140.0)
parser.add_argument("--joint-damping", type=float, default=28.0)
parser.add_argument("--target-alpha", type=float, default=0.08)
parser.add_argument("--max-joint-step", type=float, default=0.012)
parser.add_argument("--show-tcp-frames", action="store_true", help="Visualize current hand TCP and target block TCP frames.")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app


import numpy as np
import torch

from isaaclab.assets import Articulation
from isaaclab.markers import FRAME_MARKER_CFG, VisualizationMarkers

from s4_robot.arm_control import (
    KeyboardJog,
    RightArmReachController,
    CLOSE_RIGHT_HAND,
    DEFAULT_TCP_OFFSET_WRIST,
    OPEN_RIGHT_HAND,
    read_control_action,
    smooth_command,
    write_default_control_file,
)
from s4_robot.control_mapping import ACTION_SLICES, bimanual_default_action, format_action_layout
from s4_robot.s4_robot_cfg import RIGHT_ARM_JOINTS, RIGHT_HAND_JOINTS, get_joint_limits
from s4_robot.simulation import (
    DEFAULT_SCENE_USD,
    DEFAULT_TABLE_USD,
    SceneBuildCfg,
    TaskLayout,
    build_scene,
    create_simulation_context,
    format_layout,
    reset_camera,
    reset_scene,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "my_isaaclab_project" / "configs" / "s4_bimanual_dataset.json"
JOINT_LIMITS = get_joint_limits()


def load_table_top_z() -> float:
    if args_cli.table_top_z is not None:
        return float(args_cli.table_top_z)
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return float(json.load(f)["scene"]["table_top_z"])


def make_scene_cfg() -> SceneBuildCfg:
    scene_usd = args_cli.scene_usd or DEFAULT_SCENE_USD
    table_usd = args_cli.table_usd or DEFAULT_TABLE_USD
    layout = TaskLayout(
        table_center_x=float(args_cli.task_x),
        table_center_y=float(args_cli.task_y),
        block_x=float(args_cli.task_x),
        block_y_offset=float(args_cli.block_y_offset),
        plate_x=float(args_cli.plate_x),
    )
    return SceneBuildCfg(
        table_top_z=load_table_top_z(),
        joint_stiffness=float(args_cli.joint_stiffness),
        joint_damping=float(args_cli.joint_damping),
        scene_usd=scene_usd,
        table_usd=table_usd,
        robot_base_z=float(args_cli.robot_base_z),
        table_visual_z=float(args_cli.table_visual_z),
        table_scale=float(args_cli.table_scale),
        layout=layout,
    )


def set_named_joint_targets(
    full_target: np.ndarray,
    robot: Articulation,
    joint_names: list[str],
    values: np.ndarray,
) -> None:
    for name, value in zip(joint_names, values, strict=True):
        if name in robot.joint_names:
            safe_value = float(np.nan_to_num(value, nan=0.0, posinf=0.0, neginf=0.0))
            if name in JOINT_LIMITS:
                limit = JOINT_LIMITS[name]
                safe_value = float(np.clip(safe_value, limit["lower"], limit["upper"]))
            full_target[robot.joint_names.index(name)] = safe_value


def reset_unstable_arm_state(
    robot: Articulation,
    joint_names: list[str],
    full_target: np.ndarray,
    threshold_rad: float = 20.0,
) -> bool:
    joint_ids = [robot.joint_names.index(name) for name in joint_names if name in robot.joint_names]
    if not joint_ids:
        return False
    q = robot.data.joint_pos.clone()
    qd = robot.data.joint_vel.clone()
    arm_q = q[0, joint_ids]
    if torch.isfinite(arm_q).all() and float(torch.max(torch.abs(arm_q))) <= threshold_rad:
        return False
    target = torch.tensor(full_target[joint_ids], dtype=torch.float32, device=robot.device)
    q[0, joint_ids] = target
    qd[0, joint_ids] = 0.0
    robot.write_joint_state_to_sim(q, qd)
    robot.reset()
    return True


class TcpFrameVisualizer:
    """Visualize estimated hand TCP and target block TCP frames."""

    def __init__(self, device: str):
        hand_cfg = FRAME_MARKER_CFG.replace(prim_path="/World/Visuals/RightHandTCP")
        hand_cfg.markers["frame"].scale = (0.08, 0.08, 0.08)
        target_cfg = FRAME_MARKER_CFG.replace(prim_path="/World/Visuals/TargetBlockTCP")
        target_cfg.markers["frame"].scale = (0.11, 0.11, 0.11)
        self.hand_marker = VisualizationMarkers(hand_cfg)
        self.target_marker = VisualizationMarkers(target_cfg)
        self.hand_marker.set_visibility(False)
        self.target_marker.set_visibility(False)
        self.device = device
        self.identity_quat = torch.tensor([[1.0, 0.0, 0.0, 0.0]], dtype=torch.float32, device=device)

    def visualize(
        self,
        hand_tcp_pose: tuple[np.ndarray, np.ndarray] | None,
        target_tcp_pos: np.ndarray | None,
    ) -> None:
        hand_tcp_pos, hand_tcp_quat = hand_tcp_pose if hand_tcp_pose is not None else (None, None)
        if hand_tcp_pos is not None:
            pos = torch.tensor(hand_tcp_pos, dtype=torch.float32, device=self.device).view(1, 3)
            quat = torch.tensor(hand_tcp_quat, dtype=torch.float32, device=self.device).view(1, 4)
            self.hand_marker.set_visibility(True)
            self.hand_marker.visualize(translations=pos, orientations=quat)
        else:
            self.hand_marker.set_visibility(False)
        if target_tcp_pos is not None:
            pos = torch.tensor(target_tcp_pos, dtype=torch.float32, device=self.device).view(1, 3)
            self.target_marker.set_visibility(True)
            self.target_marker.visualize(translations=pos, orientations=self.identity_quat)
        else:
            self.target_marker.set_visibility(False)


def estimate_right_hand_tcp_pose(
    robot: Articulation,
    reach_controller: RightArmReachController | None,
    tcp_offset_wrist: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    if reach_controller is None:
        return None
    wrist_pose_w = robot.data.body_pose_w[:, reach_controller.right_wrist_id]
    tcp_offset = torch.tensor(tcp_offset_wrist, dtype=torch.float32, device=robot.device).view(1, 3)
    tcp_offset_w = reach_controller.rotate_wrist_vector_to_world(tcp_offset)
    tcp_pos = wrist_pose_w[0, 0:3] + tcp_offset_w[0]
    tcp_quat = wrist_pose_w[0, 3:7]
    return tcp_pos.detach().cpu().numpy(), tcp_quat.detach().cpu().numpy()


def run_debug(scene: dict[str, object], cfg: SceneBuildCfg, sim) -> None:
    robot: Articulation = scene["robot"]
    camera = scene["camera"]
    sim_dt = sim.get_physics_dt()
    default_target = reset_scene(scene, cfg, sim)
    full_command_target = default_target.copy()
    robot.set_joint_position_target(torch.tensor(full_command_target, device=sim.device).view(1, -1))
    robot.write_data_to_sim()
    action = bimanual_default_action()
    commanded_action = action.copy()
    hold_action = action.copy()

    reach_controller = None
    arm_mode = "idle"
    reach_block = None
    reach_offset = np.array([0.0, 0.0, 0.14], dtype=np.float32)
    reach_tcp_offset = DEFAULT_TCP_OFFSET_WRIST.copy()
    hand_target = OPEN_RIGHT_HAND.copy()
    test_right_arm = None
    reach_q_target = None
    reach_q_current = None
    target_tcp_pos = None
    tcp_visualizer = None
    if args_cli.show_tcp_frames and not args_cli.headless:
        tcp_visualizer = TcpFrameVisualizer(sim.device)
        reach_controller = RightArmReachController(robot, sim.device)

    keyboard_jog = None
    if args_cli.keyboard_jog and not args_cli.headless:
        candidate = KeyboardJog(action, jog_step=float(args_cli.jog_step))
        if candidate.start():
            keyboard_jog = candidate

    write_default_control_file(args_cli.control_file, overwrite=True)
    args_cli.arm_control_file.parent.mkdir(parents=True, exist_ok=True)
    args_cli.arm_control_file.write_text(json.dumps({"mode": "idle"}, indent=2), encoding="utf-8")
    print("\nS4 debug running.")
    print(format_layout(cfg))
    print(f"Joint control file: {args_cli.control_file}")
    print(f"Arm control file: {args_cli.arm_control_file}")
    print("Arm controller: idle at startup; reach command is inactive until a control command is written.")
    if tcp_visualizer is not None:
        print("TCP frames: /World/Visuals/RightHandTCP and /World/Visuals/TargetBlockTCP")
    if keyboard_jog is not None:
        print("Keyboard jog: '['/']' select joint, 'u' increase, 'j' decrease, 'r' reset, 'p' print selected.")
    print()

    try:
        last_report = time.monotonic()
        last_unstable_report = 0.0
        last_control_mtime = None
        last_arm_control_mtime = None
        while simulation_app.is_running():
            try:
                control_mtime = args_cli.control_file.stat().st_mtime_ns
            except OSError:
                control_mtime = None
            if control_mtime != last_control_mtime:
                action = read_control_action(args_cli.control_file, action)
                last_control_mtime = control_mtime
            try:
                arm_control_mtime = args_cli.arm_control_file.stat().st_mtime_ns
            except OSError:
                arm_control_mtime = None
            if arm_control_mtime != last_arm_control_mtime:
                last_arm_control_mtime = arm_control_mtime
                if arm_control_mtime is None:
                    arm_mode = "idle"
                    reach_block = None
                    target_tcp_pos = None
                else:
                    try:
                        payload = json.loads(args_cli.arm_control_file.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        print(f"[WARN] ignoring invalid arm control file: {exc}")
                    else:
                        mode = payload.get("mode", "idle")
                        if mode == "reach-block" and payload.get("block") in {"red", "blue"}:
                            arm_mode = "reach-block"
                            reach_block = payload["block"]
                            test_right_arm = None
                            reach_offset = np.asarray(payload.get("offset", [0.0, 0.0, 0.14]), dtype=np.float32)
                            if reach_offset.shape != (3,):
                                reach_offset = np.array([0.0, 0.0, 0.14], dtype=np.float32)
                            reach_tcp_offset = np.asarray(
                                payload.get("tcp_offset_wrist", DEFAULT_TCP_OFFSET_WRIST),
                                dtype=np.float32,
                            )
                            if reach_tcp_offset.shape != (3,):
                                reach_tcp_offset = DEFAULT_TCP_OFFSET_WRIST.copy()
                            hand_target = CLOSE_RIGHT_HAND.copy() if payload.get("hand") == "close" else OPEN_RIGHT_HAND.copy()
                            if reach_controller is None:
                                reach_controller = RightArmReachController(robot, sim.device)
                            print(
                                f"[ARM] reach {reach_block} cartesian-step + "
                                f"({reach_offset[0]:.3f}, {reach_offset[1]:.3f}, {reach_offset[2]:.3f}) m "
                                f"tcp_offset=({reach_tcp_offset[0]:.3f}, {reach_tcp_offset[1]:.3f}, {reach_tcp_offset[2]:.3f}) "
                                f"hand={payload.get('hand', 'open')}"
                            )
                        elif mode == "hand" and payload.get("hand") in {"open", "close"}:
                            arm_mode = "idle"
                            reach_block = None
                            test_right_arm = None
                            target_tcp_pos = None
                            hand_target = CLOSE_RIGHT_HAND.copy() if payload["hand"] == "close" else OPEN_RIGHT_HAND.copy()
                            print(f"[ARM] hand {payload['hand']}")
                        elif mode == "test-right-arm":
                            right_arm = np.asarray(payload.get("right_arm", []), dtype=np.float32)
                            if right_arm.shape == (7,):
                                arm_mode = "test-right-arm"
                                reach_block = None
                                test_right_arm = right_arm
                                target_tcp_pos = None
                                print(f"[ARM] direct right-arm target: {[round(float(x), 3) for x in right_arm]}")
                            else:
                                arm_mode = "idle"
                                reach_block = None
                                test_right_arm = None
                                target_tcp_pos = None
                                print("[ARM] idle: invalid test-right-arm target")
                        else:
                            arm_mode = "idle"
                            reach_block = None
                            test_right_arm = None
                            target_tcp_pos = None
                            print("[ARM] idle")
            if keyboard_jog is not None:
                action = keyboard_jog.update(action)

            desired_action = hold_action.copy() if arm_mode == "idle" else action.copy()
            target_pos = None
            wrist_dist = None
            if arm_mode == "reach-block" and reach_controller is not None and reach_block is not None:
                desired_action, target_pos, wrist_dist, reach_q_target, reach_q_current = reach_controller.update_action(
                    desired_action,
                    scene[reach_block],
                    reach_offset,
                    reach_tcp_offset,
                    hand_target,
                )
                target_tcp_pos = target_pos
            elif arm_mode == "test-right-arm" and test_right_arm is not None:
                desired_action[ACTION_SLICES.right_arm] = test_right_arm
                desired_action[ACTION_SLICES.right_hand] = hand_target

            commanded_action = smooth_command(
                commanded_action,
                desired_action,
                alpha=float(args_cli.target_alpha),
                max_joint_step=float(args_cli.max_joint_step),
            )
            if arm_mode == "idle":
                full_command_target = default_target.copy()
            else:
                full_command_target = default_target.copy()
                set_named_joint_targets(
                    full_command_target,
                    robot,
                    RIGHT_ARM_JOINTS,
                    commanded_action[ACTION_SLICES.right_arm],
                )
                set_named_joint_targets(
                    full_command_target,
                    robot,
                    RIGHT_HAND_JOINTS,
                    commanded_action[ACTION_SLICES.right_hand],
                )
            if hand_target is not None:
                set_named_joint_targets(full_command_target, robot, RIGHT_HAND_JOINTS, hand_target)
            if reset_unstable_arm_state(robot, RIGHT_ARM_JOINTS, full_command_target):
                now = time.monotonic()
                if now - last_unstable_report > 1.0:
                    print("[WARN] right arm joint state became unstable; reset right-arm state to clamped target.")
                    last_unstable_report = now
            robot.set_joint_position_target(torch.tensor(full_command_target, device=sim.device).view(1, -1))
            robot.write_data_to_sim()
            sim.step(render=not args_cli.headless)
            robot.update(dt=sim_dt)
            scene["red"].update(dt=sim_dt)
            scene["blue"].update(dt=sim_dt)
            scene["plate"].update(dt=sim_dt)
            camera.update(dt=sim_dt)
            if tcp_visualizer is not None:
                hand_tcp_pose = estimate_right_hand_tcp_pose(robot, reach_controller, reach_tcp_offset)
                if target_tcp_pos is None and reach_block is not None:
                    block_pos = scene[reach_block].data.root_pos_w[0].detach().cpu().numpy()
                    target_tcp_pos = block_pos + reach_offset
                tcp_visualizer.visualize(hand_tcp_pose, target_tcp_pos)

            now = time.monotonic()
            if now - last_report > 2.0:
                red_pos = scene["red"].data.root_pos_w[0].detach().cpu().numpy()
                blue_pos = scene["blue"].data.root_pos_w[0].detach().cpu().numpy()
                plate_pos = scene["plate"].data.root_pos_w[0].detach().cpu().numpy()
                status = (
                    f"red=({red_pos[0]:.3f},{red_pos[1]:.3f},{red_pos[2]:.3f}) "
                    f"blue=({blue_pos[0]:.3f},{blue_pos[1]:.3f},{blue_pos[2]:.3f}) "
                    f"plate=({plate_pos[0]:.3f},{plate_pos[1]:.3f},{plate_pos[2]:.3f})"
                )
                if target_pos is not None and wrist_dist is not None:
                    status += (
                        f" target=({target_pos[0]:.3f},{target_pos[1]:.3f},{target_pos[2]:.3f}) "
                        f"right_tcp_dist={wrist_dist:.3f}m"
                    )
                if reach_q_target is not None and reach_q_current is not None:
                    q_err = float(np.max(np.abs(reach_q_target - reach_q_current)))
                    q_lag = float(np.max(np.abs(reach_q_target - commanded_action[ACTION_SLICES.right_arm])))
                    status += f" right_arm_q_err={q_err:.3f} right_arm_cmd_lag={q_lag:.3f}"
                if arm_mode == "test-right-arm" and test_right_arm is not None:
                    q_lag = float(np.max(np.abs(test_right_arm - commanded_action[ACTION_SLICES.right_arm])))
                    status += f" direct_right_arm_cmd_lag={q_lag:.3f}"
                print(status)
                last_report = now
    finally:
        if keyboard_jog is not None:
            keyboard_jog.stop()


def main() -> None:
    cfg = make_scene_cfg()
    if args_cli.print_layout:
        print(format_action_layout())
        print(format_layout(cfg))

    sim = create_simulation_context(args_cli.device)
    scene = build_scene(cfg)
    sim.reset()
    reset_camera(scene["camera"], sim)
    run_debug(scene, cfg, sim)


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
