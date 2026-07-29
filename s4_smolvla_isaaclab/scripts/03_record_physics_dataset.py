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
parser.add_argument(
    "--clean-table-clutter",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Keep the visual table but deactivate known PackingTable clutter prims.",
)
parser.add_argument("--robot-base-z", type=float, default=0.98, help="World Z for fixed robot base_link.")
parser.add_argument("--task-x", type=float, default=0.50, help="World X for block centers.")
parser.add_argument("--task-y", type=float, default=-0.05, help="World Y center for table and task objects.")
parser.add_argument("--block-y-offset", type=float, default=0.20, help="Half spacing between red and blue blocks.")
parser.add_argument("--plate-x", type=float, default=0.50, help="World X for plate center.")
parser.add_argument("--camera-eye", type=float, nargs=3, default=[0.18, -0.62, 1.42], metavar=("X", "Y", "Z"))
parser.add_argument("--camera-target", type=float, nargs=3, default=[0.52, -0.12, 0.98], metavar=("X", "Y", "Z"))
parser.add_argument("--camera-width", type=int, default=640)
parser.add_argument("--camera-height", type=int, default=480)
parser.add_argument("--continuous", action="store_true", help="Run forever for debug.")
parser.add_argument("--keyboard-jog", action="store_true", help="Enable live keyboard joint jogging.")
parser.add_argument("--jog-step", type=float, default=0.03, help="Joint increment for keyboard jogging, in radians.")
parser.add_argument("--control-file", type=Path, default=Path("/tmp/s4_joint_command.json"))
parser.add_argument("--arm-control-file", type=Path, default=Path("/tmp/s4_arm_control.json"))
parser.add_argument("--print-layout", action="store_true")
parser.add_argument("--joint-stiffness", type=float, default=600.0)
parser.add_argument("--joint-damping", type=float, default=80.0)
parser.add_argument("--joint-effort-limit", type=float, default=300.0)
parser.add_argument("--target-alpha", type=float, default=0.18)
parser.add_argument("--max-joint-step", type=float, default=0.030)
parser.add_argument("--hand-max-joint-step", type=float, default=0.008)
parser.add_argument("--reach-max-cart-step", type=float, default=0.020)
parser.add_argument("--reach-max-joint-delta", type=float, default=0.050)
parser.add_argument("--reach-damping", type=float, default=0.16)
parser.add_argument("--reach-posture-gain", type=float, default=0.03)
parser.add_argument("--reach-max-error", type=float, default=0.85)
parser.add_argument(
    "--reach-jacobian-body-shift",
    type=int,
    default=None,
    help="Body row offset from right_wrist_yaw_link for PhysX Jacobian. Default keeps IsaacLab fixed-base convention.",
)
parser.add_argument("--reach-jacobian-sign", type=float, default=1.0, help="Set -1 to flip the raw PhysX Jacobian sign for diagnostics.")
parser.add_argument(
    "--reach-adaptive-direction-sign",
    action=argparse.BooleanOptionalAction,
    default=False,
    help="Auto-flip reach direction if measured TCP motion repeatedly moves away from the target. Disabled by default.",
)
parser.add_argument(
    "--reach-min-tcp-below-block",
    type=float,
    default=0.04,
    help="Hold reach control if TCP falls this far below the target block center.",
)
parser.add_argument("--unstable-arm-threshold", type=float, default=3.2)
parser.add_argument("--unstable-arm-velocity-threshold", type=float, default=18.0)
parser.add_argument("--reset-settle-steps", type=int, default=120, help="Physics steps to settle the robot after reset before syncing hold targets.")
parser.add_argument(
    "--gravity-compensation",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Apply PhysX joint-space gravity compensation as feed-forward effort.",
)
parser.add_argument("--gravity-comp-scale", type=float, default=1.0, help="Scale for gravity compensation feed-forward effort.")
parser.add_argument("--show-tcp-frames", action="store_true", help="Visualize current hand TCP and target block TCP frames.")
parser.add_argument("--record-output", type=Path, default=None, help="Write HDF5 episodes while running scripted grasp.")
parser.add_argument("--record-episodes", type=int, default=1, help="Number of scripted grasp episodes to record.")
parser.add_argument("--record-every-n", type=int, default=1, help="Record every N simulation steps.")
parser.add_argument(
    "--record-episode-timeout-s",
    type=float,
    default=500.0,
    help="Discard the active recorded episode and reset if it exceeds this wall-clock timeout.",
)
parser.add_argument("--auto-grasp", action="store_true", help="Automatically start grasp-block when recording starts.")
parser.add_argument("--auto-grasp-block", choices=["red", "blue"], default="blue")
parser.add_argument(
    "--randomize-blue-xy",
    type=float,
    default=0.0,
    help="Uniform per-episode randomization range for blue cylinder x/y position in meters.",
)
parser.add_argument("--random-seed", type=int, default=42, help="Seed for scripted task randomization.")
parser.add_argument(
    "--verbose-status",
    action="store_true",
    help="Print high-frequency TCP/Jacobian/status diagnostics. Default keeps logs concise.",
)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app


import numpy as np
import torch

from isaaclab.assets import Articulation
from isaaclab.markers import FRAME_MARKER_CFG, VisualizationMarkers
from isaaclab.utils.math import quat_from_euler_xyz, quat_mul

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
from s4_robot.control_mapping import ACTION_SLICES, extract_bimanual_state, format_action_layout
from s4_robot.s4_robot_cfg import ALL_DRIVE_JOINTS, RIGHT_ARM_JOINTS, RIGHT_HAND_JOINTS, get_joint_limits
from s4_robot.simulation import (
    DEFAULT_SCENE_USD,
    DEFAULT_TABLE_USD,
    SceneBuildCfg,
    TASK_OBJECT_KEYS,
    TaskLayout,
    build_scene,
    create_simulation_context,
    format_layout,
    reset_camera,
    reset_scene,
    write_object_pose,
)
from data.dataset_writer import EpisodeBuffer, Hdf5DemoWriter


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "s4_bimanual_dataset.json"
JOINT_LIMITS = get_joint_limits()


def load_table_top_z() -> float:
    if args_cli.table_top_z is not None:
        return float(args_cli.table_top_z)
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return float(json.load(f)["scene"]["table_top_z"])


def make_scene_cfg() -> SceneBuildCfg:
    scene_usd = args_cli.scene_usd or DEFAULT_SCENE_USD
    table_usd = args_cli.table_usd if args_cli.table_usd is not None else DEFAULT_TABLE_USD
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
        joint_effort_limit=float(args_cli.joint_effort_limit),
        scene_usd=scene_usd,
        table_usd=table_usd,
        robot_base_z=float(args_cli.robot_base_z),
        table_visual_z=float(args_cli.table_visual_z),
        table_scale=float(args_cli.table_scale),
        clean_table_clutter=bool(args_cli.clean_table_clutter),
        layout=layout,
        camera_eye=tuple(float(x) for x in args_cli.camera_eye),
        camera_target=tuple(float(x) for x in args_cli.camera_target),
        camera_width=max(int(args_cli.camera_width), 1),
        camera_height=max(int(args_cli.camera_height), 1),
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


def control_action_from_full_target(full_target: np.ndarray, robot: Articulation) -> np.ndarray:
    return extract_bimanual_state(full_target, robot.joint_names)


def control_action_from_sim(robot: Articulation) -> np.ndarray:
    joint_pos = robot.data.joint_pos[0].detach().cpu().numpy()
    return extract_bimanual_state(joint_pos, robot.joint_names)


def right_hand_command_error(commanded_action: np.ndarray, target: np.ndarray) -> float:
    return float(np.max(np.abs(commanded_action[ACTION_SLICES.right_hand] - np.asarray(target, dtype=np.float32))))


def pose7_from_rigid_object(obj) -> np.ndarray:
    pos = obj.data.root_pos_w[0].detach().cpu().numpy()
    quat = obj.data.root_quat_w[0].detach().cpu().numpy()
    return np.concatenate([pos, quat]).astype(np.float32)


def camera_rgb_uint8(camera) -> np.ndarray:
    rgb = camera.data.output["rgb"][0].detach().cpu().numpy()
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0.0, 1.0)
        rgb = (rgb * 255.0).astype(np.uint8)
    if rgb.shape[-1] > 3:
        rgb = rgb[..., :3]
    return rgb


def append_record_frame(
    episode: EpisodeBuffer,
    scene: dict[str, object],
    robot: Articulation,
    camera,
    action: np.ndarray,
    reach_controller: RightArmReachController | None,
    tcp_offset_wrist: np.ndarray,
) -> None:
    episode.actions.append(np.asarray(action, dtype=np.float32).copy())
    episode.full_joint_pos.append(robot.data.joint_pos[0].detach().cpu().numpy().astype(np.float32).copy())
    episode.active_joint_pos.append(control_action_from_sim(robot).astype(np.float32).copy())
    episode.chest_front_rgb.append(camera_rgb_uint8(camera))
    if reach_controller is not None:
        right_tcp = estimate_right_hand_tcp_pose(robot, reach_controller, tcp_offset_wrist)
        if right_tcp is not None:
            episode.right_eef_pose.append(np.concatenate([right_tcp[0], right_tcp[1]]).astype(np.float32))
    episode.red_block_pose.append(pose7_from_rigid_object(scene["red"]))
    episode.blue_block_pose.append(pose7_from_rigid_object(scene["blue"]))
    episode.plate_pose.append(pose7_from_rigid_object(scene["plate"]))


def default_grasp_payload(block: str) -> dict[str, object]:
    return {
        "mode": "grasp-block",
        "block": block,
        "base_offset": [-0.06, -0.05],
        "approach_z": 0.10,
        "grasp_z": 0.01,
        "lift_z": 0.15,
        "place_approach_z": 0.18,
        "place_z": 0.10,
        "place_offset": [0.0, -0.05],
        "tcp_offset_wrist": [0.0, 0.0, -0.10],
        "offset_frame": "world",
        "grasp_pose": "current",
        "grasp_rpy": [0.0, 0.1, -0.20],
        "place_rpy": [0.40, 0.0, 0.0],
        "release_lift_y": -0.05,
        "release_lift_z": 0.18,
        "release_retreat_offset": [-0.12, -0.24, 0.06],
        "tolerance": 0.05,
        "approach_steps": 120,
        "lower_steps": 120,
        "close_steps": 70,
        "hand_complete_tolerance": 0.015,
        "lift_steps": 60,
        "place_steps": 150,
        "release_steps": 50,
        "release_lift_steps": 70,
        "retreat_steps": 120,
    }


def settle_scene_to_target(scene: dict[str, object], camera, full_target: np.ndarray, sim, steps: int) -> np.ndarray:
    """Settle physics under a target, then return the settled robot joint state."""
    robot: Articulation = scene["robot"]
    steps = max(int(steps), 0)
    target_tensor = torch.tensor(full_target, dtype=torch.float32, device=robot.device).view(1, -1)
    for _ in range(steps):
        robot.set_joint_position_target(target_tensor)
        robot.write_data_to_sim()
        sim.step(render=not args_cli.headless)
        robot.update(dt=sim.get_physics_dt())
        for key in TASK_OBJECT_KEYS:
            scene[key].update(dt=sim.get_physics_dt())
        camera.update(dt=sim.get_physics_dt())
    settled = robot.data.joint_pos[0].detach().cpu().numpy().copy()
    return settled


def sample_blue_xy_offset(rng: np.random.Generator, randomize_xy: float) -> np.ndarray:
    """Sample a world-frame x/y offset for blue-object data collection."""
    span = max(float(randomize_xy), 0.0)
    if span <= 0.0:
        return np.zeros(2, dtype=np.float32)
    return rng.uniform(-span, span, size=2).astype(np.float32)


def apply_blue_xy_offset(
    scene: dict[str, object],
    cfg: SceneBuildCfg,
    sim,
    offset_xy: np.ndarray,
) -> dict[str, np.ndarray]:
    """Move only the blue cylinder by a world-frame x/y offset."""
    offset_xy = np.asarray(offset_xy, dtype=np.float32)
    if offset_xy.shape != (2,):
        raise ValueError(f"offset_xy must have shape (2,), got {offset_xy.shape}")
    block_pos = cfg.layout.blue_block_pos(cfg.table_top_z).copy()
    block_pos[:2] += offset_xy

    write_object_pose(scene["blue"], block_pos, sim.device)
    scene["blue"].update(dt=sim.get_physics_dt())
    return {"blue": block_pos}


def control_action_bias_from_target(full_target: np.ndarray, robot: Articulation) -> np.ndarray:
    """Return actuator target minus actual joint state in 26D action order."""
    return np.zeros_like(control_action_from_sim(robot))


def resolve_existing_joint_ids(robot: Articulation, joint_names: list[str]) -> list[int]:
    return [robot.joint_names.index(name) for name in joint_names if name in robot.joint_names]


def apply_gravity_compensation(
    robot: Articulation,
    joint_ids: list[int],
    scale: float,
    enabled: bool,
) -> tuple[float, float]:
    """Apply joint-space gravity compensation and return max/mean absolute effort."""
    if not joint_ids:
        return 0.0, 0.0
    if not enabled:
        zeros = torch.zeros(1, len(joint_ids), dtype=torch.float32, device=robot.device)
        robot.set_joint_effort_target(zeros, joint_ids=joint_ids)
        return 0.0, 0.0
    gravity = robot.root_physx_view.get_gravity_compensation_forces()
    if gravity.shape[1] <= max(joint_ids):
        zeros = torch.zeros(1, len(joint_ids), dtype=torch.float32, device=robot.device)
        robot.set_joint_effort_target(zeros, joint_ids=joint_ids)
        return 0.0, 0.0
    efforts = gravity[:, joint_ids] * float(scale)
    robot.set_joint_effort_target(efforts, joint_ids=joint_ids)
    abs_efforts = torch.abs(efforts)
    return float(torch.max(abs_efforts)), float(torch.mean(abs_efforts))


def reset_unstable_arm_state(
    robot: Articulation,
    joint_names: list[str],
    full_target: np.ndarray,
    threshold_rad: float,
    velocity_threshold_rad_s: float,
) -> bool:
    joint_ids = [robot.joint_names.index(name) for name in joint_names if name in robot.joint_names]
    if not joint_ids:
        return False
    q = robot.data.joint_pos.clone()
    qd = robot.data.joint_vel.clone()
    arm_q = q[0, joint_ids]
    arm_qd = qd[0, joint_ids]
    finite = torch.isfinite(arm_q).all() and torch.isfinite(arm_qd).all()
    within_position = float(torch.max(torch.abs(arm_q))) <= threshold_rad
    within_velocity = float(torch.max(torch.abs(arm_qd))) <= velocity_threshold_rad_s
    if finite and within_position and within_velocity:
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
        target_tcp_quat: np.ndarray | None = None,
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
            if target_tcp_quat is None:
                quat = self.identity_quat
            else:
                quat = torch.tensor(target_tcp_quat, dtype=torch.float32, device=self.device).view(1, 4)
            self.target_marker.set_visibility(True)
            self.target_marker.visualize(translations=pos, orientations=quat)
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


def right_tcp_position(
    robot: Articulation,
    reach_controller: RightArmReachController,
    tcp_offset_wrist: np.ndarray,
) -> np.ndarray:
    pose = estimate_right_hand_tcp_pose(robot, reach_controller, tcp_offset_wrist)
    if pose is None:
        return np.zeros(3, dtype=np.float32)
    return pose[0]


def compose_grasp_quat(
    current_tcp_quat: np.ndarray,
    rpy: np.ndarray,
    mode: str,
    device: str,
) -> np.ndarray | None:
    if mode == "none":
        return None
    if mode != "current":
        raise ValueError(f"Unsupported grasp pose mode: {mode}")
    return compose_local_rpy_quat(current_tcp_quat, rpy, device)


def compose_local_rpy_quat(
    base_quat: np.ndarray,
    rpy: np.ndarray,
    device: str,
) -> np.ndarray:
    current = torch.tensor(base_quat, dtype=torch.float32, device=device).view(1, 4)
    current = current / torch.linalg.norm(current, dim=1, keepdim=True).clamp_min(1e-6)
    rpy_t = torch.tensor(rpy, dtype=torch.float32, device=device).view(3)
    delta = quat_from_euler_xyz(rpy_t[0:1], rpy_t[1:2], rpy_t[2:3])
    target = quat_mul(current, delta)
    target = target / torch.linalg.norm(target, dim=1, keepdim=True).clamp_min(1e-6)
    return target[0].detach().cpu().numpy().astype(np.float32)


def print_right_arm_diagnostics(
    robot: Articulation,
    reach_controller: RightArmReachController,
    tcp_offset_wrist: np.ndarray,
    full_command_target: np.ndarray,
    sim,
    eps: float,
    hold_steps: int,
    drive_steps: int,
) -> None:
    eps = max(float(eps), 1e-4)
    hold_steps = max(int(hold_steps), 0)
    drive_steps = max(int(drive_steps), 0)
    joint_ids = [robot.joint_names.index(name) for name in RIGHT_ARM_JOINTS]
    q0 = robot.data.joint_pos.clone()
    qd0 = robot.data.joint_vel.clone()
    target_tensor = torch.tensor(full_command_target, dtype=torch.float32, device=robot.device).view(1, -1)
    tcp0 = right_tcp_position(robot, reach_controller, tcp_offset_wrist)
    print("[DIAG] right arm chain diagnostic begin")
    print(f"[DIAG] {reach_controller.resolution_summary()}")
    print(
        f"[DIAG] tcp0=({tcp0[0]:.5f},{tcp0[1]:.5f},{tcp0[2]:.5f}) "
        f"eps={eps:.5f} hold_steps={hold_steps} drive_steps={drive_steps}"
    )
    print(
        "[DIAG] right arm q="
        + ",".join(f"{name}:{float(q0[0, jid]):.4f}" for name, jid in zip(RIGHT_ARM_JOINTS, joint_ids, strict=True))
    )
    print(
        "[DIAG] right arm q_target="
        + ",".join(
            f"{name}:{float(full_command_target[jid]):.4f}" for name, jid in zip(RIGHT_ARM_JOINTS, joint_ids, strict=True)
        )
    )
    print(
        "[DIAG] right arm gains="
        + ",".join(
            f"{name}:kp={float(robot.data.joint_stiffness[0, jid]):.1f}/kd={float(robot.data.joint_damping[0, jid]):.1f}"
            for name, jid in zip(RIGHT_ARM_JOINTS, joint_ids, strict=True)
        )
    )
    print(
        "[DIAG] right arm effort_limits="
        + ",".join(
            f"{name}:{float(robot.data.joint_effort_limits[0, jid]):.1f}"
            for name, jid in zip(RIGHT_ARM_JOINTS, joint_ids, strict=True)
        )
    )

    if hold_steps > 0:
        hold_start = tcp0.copy()
        for _ in range(hold_steps):
            robot.set_joint_position_target(target_tensor)
            robot.write_data_to_sim()
            sim.step(render=not args_cli.headless)
            robot.update(dt=sim.get_physics_dt())
        hold_end = right_tcp_position(robot, reach_controller, tcp_offset_wrist)
        hold_delta = hold_end - hold_start
        print(
            f"[DIAG] hold_drift steps={hold_steps} "
            f"delta=({hold_delta[0]:.5f},{hold_delta[1]:.5f},{hold_delta[2]:.5f}) "
            f"tcp_end=({hold_end[0]:.5f},{hold_end[1]:.5f},{hold_end[2]:.5f})"
        )

    robot.write_joint_state_to_sim(q0, qd0)
    robot.set_joint_position_target(target_tensor)
    robot.write_data_to_sim()
    robot.update(dt=sim.get_physics_dt())
    tcp0 = right_tcp_position(robot, reach_controller, tcp_offset_wrist)

    jacobians = robot.root_physx_view.get_jacobians()
    candidate_rows = []
    for row in [reach_controller.right_wrist_id - 1, reach_controller.right_wrist_id]:
        if 0 <= row < jacobians.shape[1] and row not in candidate_rows:
            candidate_rows.append(row)
    tcp_offset_t = torch.tensor(tcp_offset_wrist, dtype=torch.float32, device=robot.device).view(1, 3)
    tcp_offset_w = reach_controller.rotate_wrist_vector_to_world(tcp_offset_t)

    jac_cols_by_row = {}
    for row in candidate_rows:
        jac = jacobians[:, row, :, joint_ids]
        linear = jac[:, 0:3, :]
        angular = jac[:, 3:6, :]
        offset_cols = tcp_offset_w.unsqueeze(-1).expand_as(angular)
        tcp_jac = linear + torch.cross(angular, offset_cols, dim=1)
        jac_cols_by_row[row] = tcp_jac[0].detach().cpu().numpy()

    for local_i, (name, jid) in enumerate(zip(RIGHT_ARM_JOINTS, joint_ids, strict=True)):
        q_plus = q0.clone()
        q_minus = q0.clone()
        q_plus[0, jid] += eps
        q_minus[0, jid] -= eps
        robot.write_joint_state_to_sim(q_plus, torch.zeros_like(q_plus))
        robot.update(dt=sim.get_physics_dt())
        tcp_plus = right_tcp_position(robot, reach_controller, tcp_offset_wrist)
        robot.write_joint_state_to_sim(q_minus, torch.zeros_like(q_minus))
        robot.update(dt=sim.get_physics_dt())
        tcp_minus = right_tcp_position(robot, reach_controller, tcp_offset_wrist)
        fd_col = (tcp_plus - tcp_minus) / (2.0 * eps)
        row_parts = []
        for row, cols in jac_cols_by_row.items():
            col = cols[:, local_i]
            denom = max(float(np.linalg.norm(fd_col) * np.linalg.norm(col)), 1e-8)
            cos = float(np.dot(fd_col, col) / denom)
            row_parts.append(f"row{row}=({col[0]:+.4f},{col[1]:+.4f},{col[2]:+.4f}) cos={cos:+.3f}")
        print(
            f"[DIAG] fd {name}[id={jid}] "
            f"fd=({fd_col[0]:+.4f},{fd_col[1]:+.4f},{fd_col[2]:+.4f}) "
            + " ".join(row_parts)
        )

    if drive_steps > 0:
        print(f"[DIAG] positive joint-target response begin drive_steps={drive_steps}")
        for name, jid in zip(RIGHT_ARM_JOINTS, joint_ids, strict=True):
            hold_target = target_tensor.clone()
            robot.write_joint_state_to_sim(q0, torch.zeros_like(q0))
            robot.set_joint_position_target(hold_target)
            robot.write_data_to_sim()
            robot.reset()
            robot.update(dt=sim.get_physics_dt())
            for _ in range(4):
                robot.set_joint_position_target(hold_target)
                robot.write_data_to_sim()
                sim.step(render=not args_cli.headless)
                robot.update(dt=sim.get_physics_dt())
            q_start = robot.data.joint_pos.clone()
            tcp_start = right_tcp_position(robot, reach_controller, tcp_offset_wrist)
            drive_target = hold_target.clone()
            drive_target[0, jid] = drive_target[0, jid] + eps
            for _ in range(drive_steps):
                robot.set_joint_position_target(drive_target)
                robot.write_data_to_sim()
                sim.step(render=not args_cli.headless)
                robot.update(dt=sim.get_physics_dt())
            q_end = float(robot.data.joint_pos[0, jid])
            right_q_delta = (robot.data.joint_pos[0, joint_ids] - q_start[0, joint_ids]).detach().cpu().numpy()
            q_delta = q_end - float(q_start[0, jid])
            tcp_delta = right_tcp_position(robot, reach_controller, tcp_offset_wrist) - tcp_start
            print(
                f"[DIAG] drive+ {name}[id={jid}] target_delta=+{eps:.5f} q_delta={q_delta:+.5f} "
                f"tcp_delta=({tcp_delta[0]:+.5f},{tcp_delta[1]:+.5f},{tcp_delta[2]:+.5f}) "
                f"all_right_dq=({','.join(f'{x:+.5f}' for x in right_q_delta)})"
            )
        print("[DIAG] positive joint-target response end")

    robot.write_joint_state_to_sim(q0, qd0)
    robot.set_joint_position_target(target_tensor)
    robot.write_data_to_sim()
    robot.reset()
    robot.update(dt=sim.get_physics_dt())
    print("[DIAG] right arm chain diagnostic end")


def make_right_reach_controller(robot: Articulation, device: str) -> RightArmReachController:
    return RightArmReachController(
        robot,
        device,
        max_cart_step=float(args_cli.reach_max_cart_step),
        max_joint_delta=float(args_cli.reach_max_joint_delta),
        damping=float(args_cli.reach_damping),
        posture_gain=float(args_cli.reach_posture_gain),
        max_reach_error=float(args_cli.reach_max_error),
        jacobian_body_shift=args_cli.reach_jacobian_body_shift,
        jacobian_sign=float(args_cli.reach_jacobian_sign),
        adaptive_direction_sign=bool(args_cli.reach_adaptive_direction_sign),
        min_tcp_below_block=float(args_cli.reach_min_tcp_below_block),
    )


def run_debug(scene: dict[str, object], cfg: SceneBuildCfg, sim) -> None:
    robot: Articulation = scene["robot"]
    camera = scene["camera"]
    sim_dt = sim.get_physics_dt()
    rng = np.random.default_rng(int(args_cli.random_seed))
    randomize_blue_xy = max(float(args_cli.randomize_blue_xy), 0.0)
    default_target = reset_scene(scene, cfg, sim)
    blue_offset_xy = sample_blue_xy_offset(rng, randomize_blue_xy)
    blue_randomized = apply_blue_xy_offset(scene, cfg, sim, blue_offset_xy)
    if randomize_blue_xy > 0.0:
        blue_pos = blue_randomized["blue"]
        print(
            f"[RANDOMIZE] blue xy offset=({blue_offset_xy[0]:+.4f},{blue_offset_xy[1]:+.4f}) "
            f"blue=({blue_pos[0]:.3f},{blue_pos[1]:.3f},{blue_pos[2]:.3f})"
        )
    settle_scene_to_target(scene, camera, default_target, sim, args_cli.reset_settle_steps)
    full_command_target = default_target.copy()
    robot.set_joint_position_target(torch.tensor(full_command_target, device=sim.device).view(1, -1))
    robot.write_data_to_sim()
    action = control_action_from_sim(robot)
    commanded_action = action.copy()
    hold_action = action.copy()
    action_target_bias = control_action_bias_from_target(full_command_target, robot)

    reach_controller = None
    arm_mode = "idle"
    reach_block = None
    reach_offset = np.array([0.0, 0.0, 0.14], dtype=np.float32)
    reach_offset_frame = "world"
    reach_tcp_offset = DEFAULT_TCP_OFFSET_WRIST.copy()
    hand_target = OPEN_RIGHT_HAND.copy()
    test_right_arm = None
    reach_q_target = None
    reach_q_current = None
    target_tcp_pos = None
    target_tcp_quat = None
    grasp_plan = None
    grasp_phase = None
    grasp_phase_steps = 0
    gravity_comp_joint_ids = resolve_existing_joint_ids(robot, list(ALL_DRIVE_JOINTS))
    last_gravity_comp_stats = (0.0, 0.0)
    tcp_visualizer = None
    writer = None
    recording_episode = None
    recorded_episodes = 0
    record_step = 0
    record_wall_start = None
    auto_grasp_pending = bool(args_cli.auto_grasp or args_cli.record_output is not None)
    max_record_episodes = max(int(args_cli.record_episodes), 1)
    record_every_n = max(int(args_cli.record_every_n), 1)
    if args_cli.record_output is not None:
        writer = Hdf5DemoWriter(
            args_cli.record_output,
            env_args={
                "task": "s4_right_blue_cylinder_plate_scripted",
                "source": "scripted_ik",
                "sim_dt": float(sim.get_physics_dt()),
                "record_every_n": int(record_every_n),
                "record_episode_timeout_s": float(max(float(args_cli.record_episode_timeout_s), 1.0)),
                "record_fps": float(1.0 / (sim.get_physics_dt() * record_every_n)),
                "randomization": {
                    "blue_xy_range_m": float(randomize_blue_xy),
                    "random_seed": int(args_cli.random_seed),
                    "distribution": "uniform",
                },
                "camera": {
                    "eye": list(cfg.camera_eye),
                    "target": list(cfg.camera_target),
                    "width": int(cfg.camera_width),
                    "height": int(cfg.camera_height),
                },
                "layout": {
                    "task_x": float(cfg.layout.block_x),
                    "task_y": float(cfg.layout.table_center_y),
                    "block_y_offset": float(cfg.layout.block_y_offset),
                    "plate_x": float(cfg.layout.plate_x),
                },
            },
        )
    if args_cli.show_tcp_frames and not args_cli.headless:
        tcp_visualizer = TcpFrameVisualizer(sim.device)
        reach_controller = make_right_reach_controller(robot, sim.device)
        if args_cli.verbose_status:
            print(f"[ARM] reach resolution: {reach_controller.resolution_summary()}")

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
    if tcp_visualizer is not None:
        print("TCP frames: /World/Visuals/RightHandTCP and /World/Visuals/TargetBlockTCP")
    if keyboard_jog is not None:
        print("Keyboard jog: '['/']' select joint, 'u' increase, 'j' decrease, 'r' reset, 'p' print selected.")
    print("Reset command: bash run.sh control reset-scene")
    if writer is not None:
        print(
            f"HDF5 recording: {args_cli.record_output} episodes={max_record_episodes} "
            f"every_n={record_every_n} timeout={max(float(args_cli.record_episode_timeout_s), 1.0):.1f}s"
        )
    if args_cli.verbose_status:
        print(f"Joint control file: {args_cli.control_file}")
        print(f"Arm control file: {args_cli.arm_control_file}")
        print("Arm controller: idle at startup; reach command is inactive until a control command is written.")
        print(
            f"Robot dynamics: fixed_base={robot.is_fixed_base} "
            f"joint_stiffness={float(args_cli.joint_stiffness):.1f} "
            f"joint_damping={float(args_cli.joint_damping):.1f} "
            f"joint_effort_limit={float(args_cli.joint_effort_limit):.1f} "
            f"gravity_compensation={bool(args_cli.gravity_compensation)} "
            f"gravity_comp_scale={float(args_cli.gravity_comp_scale):.2f}"
        )
        print("Reach controller: IsaacLab DifferentialIKController, root-frame TCP target, PhysX geometric Jacobian.")
        print(
            "Reach Jacobian params: "
            f"body_shift={args_cli.reach_jacobian_body_shift} "
            f"sign={float(args_cli.reach_jacobian_sign):.1f} "
            f"adaptive_direction_sign={bool(args_cli.reach_adaptive_direction_sign)} "
            f"min_tcp_below_block={float(args_cli.reach_min_tcp_below_block):.3f}m"
        )
        print(f"Hand smoothing: max_joint_step={float(args_cli.hand_max_joint_step):.4f} rad/step")
    print()

    try:
        last_report = time.monotonic()
        last_unstable_report = 0.0
        last_grasp_wait_report = 0.0
        last_control_mtime = None
        last_arm_control_mtime = None
        while simulation_app.is_running():
            if auto_grasp_pending:
                args_cli.arm_control_file.write_text(
                    json.dumps(default_grasp_payload(args_cli.auto_grasp_block), indent=2),
                    encoding="utf-8",
                )
                auto_grasp_pending = False
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
                    target_tcp_quat = None
                else:
                    try:
                        payload = json.loads(args_cli.arm_control_file.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        print(f"[WARN] ignoring invalid arm control file: {exc}")
                    else:
                        mode = payload.get("mode", "idle")
                        if mode in {"reach-block", "grasp-block"} and payload.get("block") in {"red", "blue"}:
                            arm_mode = mode
                            reach_block = payload["block"]
                            test_right_arm = None
                            action = control_action_from_sim(robot)
                            commanded_action = action.copy()
                            hold_action = action.copy()
                            action_target_bias = control_action_bias_from_target(full_command_target, robot)
                            target_tcp_quat = None
                            if mode == "grasp-block":
                                if writer is not None:
                                    recording_episode = EpisodeBuffer()
                                    record_step = 0
                                base_offset = np.asarray(payload.get("base_offset", [0.0, 0.0]), dtype=np.float32)
                                if base_offset.shape != (2,):
                                    base_offset = np.array([0.0, 0.0], dtype=np.float32)
                                grasp_plan = {
                                    "base_offset": base_offset,
                                    "approach_z": float(payload.get("approach_z", 0.10)),
                                    "grasp_z": float(payload.get("grasp_z", 0.01)),
                                    "lift_z": float(payload.get("lift_z", 0.15)),
                                    "place_approach_z": float(payload.get("place_approach_z", 0.18)),
                                    "place_z": float(payload.get("place_z", 0.10)),
                                    "place_offset": np.asarray(payload.get("place_offset", [0.0, -0.05]), dtype=np.float32),
                                    "grasp_pose": payload.get("grasp_pose", "current"),
                                    "grasp_rpy": np.asarray(payload.get("grasp_rpy", [0.0, 0.1, -0.20]), dtype=np.float32),
                                    "place_rpy": np.asarray(payload.get("place_rpy", [0.40, 0.0, 0.0]), dtype=np.float32),
                                    "release_lift_y": float(payload.get("release_lift_y", -0.05)),
                                    "release_lift_z": float(payload.get("release_lift_z", 0.18)),
                                    "release_retreat_offset": np.asarray(
                                        payload.get("release_retreat_offset", [-0.12, -0.24, 0.06]),
                                        dtype=np.float32,
                                    ),
                                    "tolerance": max(float(payload.get("tolerance", 0.05)), 0.01),
                                    "approach_steps": max(int(payload.get("approach_steps", 360)), 1),
                                    "lower_steps": max(int(payload.get("lower_steps", 240)), 1),
                                    "close_steps": max(int(payload.get("close_steps", 160)), 1),
                                    "hand_complete_tolerance": max(float(payload.get("hand_complete_tolerance", 0.015)), 0.001),
                                    "lift_steps": max(int(payload.get("lift_steps", 120)), 1),
                                    "place_steps": max(int(payload.get("place_steps", 360)), 1),
                                    "release_steps": max(int(payload.get("release_steps", 120)), 1),
                                    "release_lift_steps": max(int(payload.get("release_lift_steps", 70)), 1),
                                    "retreat_steps": max(int(payload.get("retreat_steps", 360)), 1),
                                }
                                if grasp_plan["place_offset"].shape != (2,):
                                    grasp_plan["place_offset"] = np.array([0.0, -0.05], dtype=np.float32)
                                if grasp_plan["release_retreat_offset"].shape != (3,):
                                    grasp_plan["release_retreat_offset"] = np.array([-0.12, -0.24, 0.06], dtype=np.float32)
                                grasp_phase = "approach"
                                grasp_phase_steps = 0
                                reach_offset = np.array(
                                    [base_offset[0], base_offset[1], grasp_plan["approach_z"]],
                                    dtype=np.float32,
                                )
                            else:
                                grasp_plan = None
                                grasp_phase = None
                                grasp_phase_steps = 0
                                reach_offset = np.asarray(payload.get("offset", [0.0, 0.0, 0.20]), dtype=np.float32)
                                if reach_offset.shape != (3,):
                                    reach_offset = np.array([0.0, 0.0, 0.20], dtype=np.float32)
                            reach_offset_frame = payload.get("offset_frame", "world")
                            if reach_offset_frame not in {"world", "wrist"}:
                                reach_offset_frame = "world"
                            reach_tcp_offset = np.asarray(
                                payload.get("tcp_offset_wrist", DEFAULT_TCP_OFFSET_WRIST),
                                dtype=np.float32,
                            )
                            if reach_tcp_offset.shape != (3,):
                                reach_tcp_offset = DEFAULT_TCP_OFFSET_WRIST.copy()
                            hand_target = CLOSE_RIGHT_HAND.copy() if payload.get("hand") == "close" else OPEN_RIGHT_HAND.copy()
                            if mode == "grasp-block":
                                hand_target = OPEN_RIGHT_HAND.copy()
                                if writer is not None:
                                    record_wall_start = time.monotonic()
                            if reach_controller is None:
                                reach_controller = make_right_reach_controller(robot, sim.device)
                                print(f"[ARM] reach resolution: {reach_controller.resolution_summary()}")
                            else:
                                reach_controller.reset_diagnostics()
                            block_pos = scene[reach_block].data.root_pos_w[0].detach().cpu().numpy()
                            if mode == "grasp-block":
                                grasp_plan["anchor_block_pos_w"] = block_pos.copy()
                                grasp_plan["anchor_plate_pos_w"] = scene["plate"].data.root_pos_w[0].detach().cpu().numpy().copy()
                            if reach_offset_frame == "world":
                                preview_offset_w = reach_offset
                            else:
                                offset_t = torch.tensor(reach_offset, dtype=torch.float32, device=sim.device).view(1, 3)
                                preview_offset_w = reach_controller.rotate_wrist_vector_to_world(offset_t)[0].detach().cpu().numpy()
                            preview_target_tcp = block_pos + preview_offset_w
                            current_tcp_pose = estimate_right_hand_tcp_pose(robot, reach_controller, reach_tcp_offset)
                            current_tcp = current_tcp_pose[0] if current_tcp_pose is not None else np.zeros(3, dtype=np.float32)
                            current_tcp_quat = (
                                current_tcp_pose[1] if current_tcp_pose is not None else np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
                            )
                            if mode == "grasp-block":
                                grasp_pose_mode = grasp_plan.get("grasp_pose", "current")
                                grasp_rpy = grasp_plan.get("grasp_rpy", np.zeros(3, dtype=np.float32))
                                if np.asarray(grasp_rpy).shape != (3,):
                                    grasp_rpy = np.zeros(3, dtype=np.float32)
                                target_tcp_quat = compose_grasp_quat(
                                    current_tcp_quat,
                                    np.asarray(grasp_rpy, dtype=np.float32),
                                    grasp_pose_mode,
                                    sim.device,
                                )
                                grasp_plan["target_tcp_quat_w"] = None if target_tcp_quat is None else target_tcp_quat.copy()
                                grasp_plan["carry_tcp_quat_w"] = None
                                grasp_plan["place_tcp_quat_w"] = None
                                grasp_plan["active_target_tcp_quat_w"] = (
                                    None if target_tcp_quat is None else target_tcp_quat.copy()
                                )
                            preview_delta = preview_target_tcp - current_tcp
                            if mode == "grasp-block":
                                print(
                                    f"[ARM] grasp {reach_block}: approach_z={grasp_plan['approach_z']:.3f} "
                                    f"grasp_z={grasp_plan['grasp_z']:.3f} lift_z={grasp_plan['lift_z']:.3f} "
                                    f"tol={grasp_plan['tolerance']:.3f} offset_frame={reach_offset_frame} "
                                    f"grasp_pose={grasp_plan['grasp_pose']} "
                                    f"place_offset=({grasp_plan['place_offset'][0]:.3f},{grasp_plan['place_offset'][1]:.3f}) "
                                    f"grasp_rpy=({grasp_plan['grasp_rpy'][0]:.3f},{grasp_plan['grasp_rpy'][1]:.3f},{grasp_plan['grasp_rpy'][2]:.3f}) "
                                    f"place_rpy=({grasp_plan['place_rpy'][0]:.3f},{grasp_plan['place_rpy'][1]:.3f},{grasp_plan['place_rpy'][2]:.3f}) "
                                    f"tcp_offset=({reach_tcp_offset[0]:.3f}, {reach_tcp_offset[1]:.3f}, {reach_tcp_offset[2]:.3f})"
                                )
                                print(
                                    f"[ARM] grasp anchor locked in fixed world/base frame: "
                                    f"({block_pos[0]:.3f},{block_pos[1]:.3f},{block_pos[2]:.3f})"
                                )
                                plate_anchor = grasp_plan["anchor_plate_pos_w"]
                                print(
                                    f"[ARM] plate anchor locked in fixed world/base frame: "
                                    f"({plate_anchor[0]:.3f},{plate_anchor[1]:.3f},{plate_anchor[2]:.3f})"
                                )
                                if target_tcp_quat is not None:
                                    print(
                                        f"[ARM] grasp approach TCP quat locked: "
                                        f"({target_tcp_quat[0]:.4f},{target_tcp_quat[1]:.4f},"
                                        f"{target_tcp_quat[2]:.4f},{target_tcp_quat[3]:.4f})"
                                    )
                            else:
                                print(
                                    f"[ARM] reach {reach_block} cartesian-step + "
                                    f"({reach_offset[0]:.3f}, {reach_offset[1]:.3f}, {reach_offset[2]:.3f}) m "
                                    f"offset_frame={reach_offset_frame} "
                                    f"tcp_offset=({reach_tcp_offset[0]:.3f}, {reach_tcp_offset[1]:.3f}, {reach_tcp_offset[2]:.3f}) "
                                    f"hand={payload.get('hand', 'open')}"
                                )
                            print(
                                f"[ARM] preview block=({block_pos[0]:.3f},{block_pos[1]:.3f},{block_pos[2]:.3f}) "
                                f"target_tcp=({preview_target_tcp[0]:.3f},{preview_target_tcp[1]:.3f},{preview_target_tcp[2]:.3f}) "
                                f"tcp=({current_tcp[0]:.3f},{current_tcp[1]:.3f},{current_tcp[2]:.3f}) "
                                f"target_minus_tcp=({preview_delta[0]:+.3f},{preview_delta[1]:+.3f},{preview_delta[2]:+.3f})"
                            )
                            if preview_delta[2] < -0.005:
                                print(
                                    "[WARN] reach target is below the current TCP in world Z; "
                                    "the first motion will intentionally include a downward component. "
                                    "Use a larger --z-offset for an above-block approach."
                                )
                        elif mode == "hand" and payload.get("hand") in {"open", "close"}:
                            arm_mode = "hold"
                            reach_block = None
                            test_right_arm = None
                            target_tcp_pos = None
                            target_tcp_quat = None
                            grasp_plan = None
                            grasp_phase = None
                            grasp_phase_steps = 0
                            action = control_action_from_sim(robot)
                            commanded_action = action.copy()
                            hold_action = action.copy()
                            action_target_bias = control_action_bias_from_target(full_command_target, robot)
                            hand_target = CLOSE_RIGHT_HAND.copy() if payload["hand"] == "close" else OPEN_RIGHT_HAND.copy()
                            print(f"[ARM] hand {payload['hand']} while holding current right-arm state")
                        elif mode == "test-right-arm":
                            right_arm = np.asarray(payload.get("right_arm", []), dtype=np.float32)
                            if right_arm.shape == (7,):
                                arm_mode = "test-right-arm"
                                reach_block = None
                                test_right_arm = right_arm
                                target_tcp_pos = None
                                target_tcp_quat = None
                                print(f"[ARM] direct right-arm target: {[round(float(x), 3) for x in right_arm]}")
                            else:
                                arm_mode = "idle"
                                reach_block = None
                                test_right_arm = None
                                target_tcp_pos = None
                                target_tcp_quat = None
                                print("[ARM] idle: invalid test-right-arm target")
                        elif mode == "reset-scene":
                            default_target = reset_scene(scene, cfg, sim)
                            blue_offset_xy = sample_blue_xy_offset(rng, randomize_blue_xy)
                            blue_randomized = apply_blue_xy_offset(scene, cfg, sim, blue_offset_xy)
                            if randomize_blue_xy > 0.0:
                                blue_pos = blue_randomized["blue"]
                                print(
                                    f"[RANDOMIZE] blue xy offset=({blue_offset_xy[0]:+.4f},{blue_offset_xy[1]:+.4f}) "
                                    f"blue=({blue_pos[0]:.3f},{blue_pos[1]:.3f},{blue_pos[2]:.3f})"
                                )
                            reset_camera(camera, sim, cfg)
                            settle_scene_to_target(
                                scene,
                                camera,
                                default_target,
                                sim,
                                args_cli.reset_settle_steps,
                            )
                            full_command_target = default_target.copy()
                            action = control_action_from_sim(robot)
                            commanded_action = action.copy()
                            hold_action = action.copy()
                            action_target_bias = control_action_bias_from_target(full_command_target, robot)
                            arm_mode = "idle"
                            reach_block = None
                            test_right_arm = None
                            target_tcp_pos = None
                            target_tcp_quat = None
                            grasp_plan = None
                            grasp_phase = None
                            grasp_phase_steps = 0
                            reach_q_target = None
                            reach_q_current = None
                            hand_target = OPEN_RIGHT_HAND.copy()
                            reach_offset_frame = "world"
                            if reach_controller is not None:
                                reach_controller.reset_diagnostics()
                            robot.set_joint_position_target(torch.tensor(full_command_target, device=sim.device).view(1, -1))
                            robot.write_data_to_sim()
                            print(f"[SCENE] reset robot, task objects, camera, and control state after {args_cli.reset_settle_steps} settle steps.")
                        elif mode == "diagnose-right-arm":
                            arm_mode = "idle"
                            reach_block = None
                            test_right_arm = None
                            target_tcp_pos = None
                            target_tcp_quat = None
                            grasp_plan = None
                            grasp_phase = None
                            grasp_phase_steps = 0
                            if reach_controller is None:
                                reach_controller = make_right_reach_controller(robot, sim.device)
                                print(f"[ARM] reach resolution: {reach_controller.resolution_summary()}")
                            diag_eps = float(payload.get("eps", 0.01))
                            diag_hold_steps = int(payload.get("hold_steps", 60))
                            diag_drive_steps = int(payload.get("drive_steps", 30))
                            print_right_arm_diagnostics(
                                robot,
                                reach_controller,
                                reach_tcp_offset,
                                full_command_target,
                                sim,
                                eps=diag_eps,
                                hold_steps=diag_hold_steps,
                                drive_steps=diag_drive_steps,
                            )
                            action = control_action_from_sim(robot)
                            commanded_action = action.copy()
                            hold_action = action.copy()
                            action_target_bias = control_action_bias_from_target(full_command_target, robot)
                            args_cli.arm_control_file.write_text(json.dumps({"mode": "idle"}, indent=2), encoding="utf-8")
                            print("[ARM] idle after diagnostics")
                        else:
                            arm_mode = "idle"
                            reach_block = None
                            test_right_arm = None
                            target_tcp_pos = None
                            target_tcp_quat = None
                            grasp_plan = None
                            grasp_phase = None
                            grasp_phase_steps = 0
                            print("[ARM] idle")
            if keyboard_jog is not None:
                action = keyboard_jog.update(action)

            desired_action = hold_action.copy() if arm_mode in {"idle", "hold"} else commanded_action.copy()
            target_pos = None
            reach_debug = None
            if arm_mode == "grasp-block" and grasp_plan is not None and reach_block is not None:
                grasp_phase_steps += 1
                block_anchor = grasp_plan.get("anchor_block_pos_w")
                if block_anchor is None:
                    block_anchor = scene[reach_block].data.root_pos_w[0].detach().cpu().numpy()
                plate_anchor = grasp_plan.get("anchor_plate_pos_w")
                if plate_anchor is None:
                    plate_anchor = scene["plate"].data.root_pos_w[0].detach().cpu().numpy()
                base_offset = grasp_plan["base_offset"]
                place_offset = grasp_plan["place_offset"]
                block_phase_offsets = {
                    "approach": np.array([base_offset[0], base_offset[1], grasp_plan["approach_z"]], dtype=np.float32),
                    "lower": np.array([base_offset[0], base_offset[1], grasp_plan["grasp_z"]], dtype=np.float32),
                    "close": np.array([base_offset[0], base_offset[1], grasp_plan["grasp_z"]], dtype=np.float32),
                    "lift": np.array([base_offset[0], base_offset[1], grasp_plan["lift_z"]], dtype=np.float32),
                }
                plate_phase_offsets = {
                    "move_to_plate": np.array(
                        [place_offset[0], place_offset[1], grasp_plan["place_approach_z"]],
                        dtype=np.float32,
                    ),
                    "place_lower": np.array(
                        [place_offset[0], place_offset[1], grasp_plan["place_z"]],
                        dtype=np.float32,
                    ),
                    "release": np.array(
                        [place_offset[0], place_offset[1], grasp_plan["place_z"]],
                        dtype=np.float32,
                    ),
                    "release_lift": np.array(
                        [0.0, grasp_plan["release_lift_y"], grasp_plan["release_lift_z"]],
                        dtype=np.float32,
                    ),
                    "release_retreat": np.asarray(grasp_plan["release_retreat_offset"], dtype=np.float32),
                }
                if grasp_phase in {"release_lift", "release_retreat"}:
                    phase_anchor_key = f"{grasp_phase}_anchor_pos_w"
                    phase_anchor = grasp_plan.get(phase_anchor_key)
                    if phase_anchor is None:
                        phase_anchor = plate_anchor
                    phase_offset = plate_phase_offsets[grasp_phase]
                elif grasp_phase in plate_phase_offsets:
                    phase_anchor = plate_anchor
                    phase_offset = plate_phase_offsets[grasp_phase]
                else:
                    phase_anchor = block_anchor
                    phase_offset = block_phase_offsets.get(grasp_phase, block_phase_offsets["approach"])
                if reach_controller is not None:
                    if grasp_phase in {"release_lift", "release_retreat"} or reach_offset_frame == "world":
                        phase_offset_w = phase_offset
                    else:
                        offset_t = torch.tensor(phase_offset, dtype=torch.float32, device=sim.device).view(1, 3)
                        phase_offset_w = reach_controller.rotate_wrist_vector_to_world(offset_t)[0].detach().cpu().numpy()
                    current_tcp_pose = estimate_right_hand_tcp_pose(robot, reach_controller, reach_tcp_offset)
                    current_tcp = current_tcp_pose[0] if current_tcp_pose is not None else np.zeros(3, dtype=np.float32)
                    phase_dist = float(np.linalg.norm(phase_anchor + phase_offset_w - current_tcp))
                else:
                    phase_dist = float("inf")
                old_phase = grasp_phase
                current_tcp_pose = None
                current_tcp_quat = None
                if reach_controller is not None:
                    current_tcp_pose = estimate_right_hand_tcp_pose(robot, reach_controller, reach_tcp_offset)
                    if current_tcp_pose is not None:
                        current_tcp_quat = current_tcp_pose[1]
                if grasp_phase == "approach" and (
                    phase_dist <= grasp_plan["tolerance"] or grasp_phase_steps >= grasp_plan["approach_steps"]
                ):
                    grasp_phase = "lower"
                    grasp_phase_steps = 0
                elif grasp_phase == "lower":
                    if phase_dist <= grasp_plan["tolerance"]:
                        grasp_phase = "close"
                        grasp_phase_steps = 0
                    elif grasp_phase_steps >= grasp_plan["lower_steps"]:
                        now = time.monotonic()
                        if now - last_grasp_wait_report > 1.0:
                            print(
                                "[ARM] waiting at lower target before closing: "
                                f"dist={phase_dist:.3f}m tol={grasp_plan['tolerance']:.3f}m. "
                                "The hand will not close high; tune --grasp-z/--tolerance if this stays stuck."
                            )
                            last_grasp_wait_report = now
                        grasp_phase_steps = grasp_plan["lower_steps"]
                elif grasp_phase == "close":
                    hand_err = right_hand_command_error(commanded_action, CLOSE_RIGHT_HAND)
                    if grasp_phase_steps >= grasp_plan["close_steps"] and hand_err <= grasp_plan["hand_complete_tolerance"]:
                        grasp_phase = "lift"
                        grasp_phase_steps = 0
                        if current_tcp_quat is not None:
                            grasp_plan["carry_tcp_quat_w"] = current_tcp_quat.copy()
                            place_rpy = grasp_plan.get("place_rpy", np.zeros(3, dtype=np.float32))
                            if np.asarray(place_rpy).shape != (3,):
                                place_rpy = np.zeros(3, dtype=np.float32)
                            grasp_plan["place_tcp_quat_w"] = compose_local_rpy_quat(
                                current_tcp_quat,
                                np.asarray(place_rpy, dtype=np.float32),
                                sim.device,
                            )
                            if args_cli.verbose_status:
                                print(
                                    "[ARM] carry/place TCP quat locked from actual grasp pose: "
                                    f"({current_tcp_quat[0]:.4f},{current_tcp_quat[1]:.4f},"
                                    f"{current_tcp_quat[2]:.4f},{current_tcp_quat[3]:.4f})"
                                )
                                place_quat = grasp_plan["place_tcp_quat_w"]
                                print(
                                    "[ARM] place TCP quat with local x-roll offset: "
                                    f"({place_quat[0]:.4f},{place_quat[1]:.4f},"
                                    f"{place_quat[2]:.4f},{place_quat[3]:.4f})"
                                )
                    elif grasp_phase_steps >= grasp_plan["close_steps"]:
                        now = time.monotonic()
                        if now - last_grasp_wait_report > 1.0:
                            print(
                                "[ARM] waiting for hand close before lifting: "
                                f"cmd_err={hand_err:.3f} tol={grasp_plan['hand_complete_tolerance']:.3f}"
                            )
                            last_grasp_wait_report = now
                        grasp_phase_steps = grasp_plan["close_steps"]
                elif grasp_phase == "lift" and (
                    phase_dist <= grasp_plan["tolerance"] or grasp_phase_steps >= grasp_plan["lift_steps"]
                ):
                    grasp_phase = "move_to_plate"
                    grasp_phase_steps = 0
                elif grasp_phase == "move_to_plate" and (
                    phase_dist <= grasp_plan["tolerance"] or grasp_phase_steps >= grasp_plan["place_steps"]
                ):
                    grasp_phase = "place_lower"
                    grasp_phase_steps = 0
                elif grasp_phase == "place_lower":
                    if phase_dist <= grasp_plan["tolerance"]:
                        grasp_phase = "release"
                        grasp_phase_steps = 0
                    elif grasp_phase_steps >= grasp_plan["place_steps"]:
                        now = time.monotonic()
                        if now - last_grasp_wait_report > 1.0:
                            print(
                                "[ARM] waiting at plate release target before opening: "
                                f"dist={phase_dist:.3f}m tol={grasp_plan['tolerance']:.3f}m. "
                                "The hand will not open high; tune --place-z/--tolerance if this stays stuck."
                            )
                            last_grasp_wait_report = now
                        grasp_phase_steps = grasp_plan["place_steps"]
                elif grasp_phase == "release":
                    hand_err = right_hand_command_error(commanded_action, OPEN_RIGHT_HAND)
                    if grasp_phase_steps >= grasp_plan["release_steps"] and hand_err <= grasp_plan["hand_complete_tolerance"]:
                        commanded_action[ACTION_SLICES.right_hand] = OPEN_RIGHT_HAND.copy()
                        desired_action[ACTION_SLICES.right_hand] = OPEN_RIGHT_HAND.copy()
                        hand_target = OPEN_RIGHT_HAND.copy()
                        if current_tcp_pose is not None:
                            grasp_plan["release_lift_anchor_pos_w"] = current_tcp_pose[0].copy()
                        else:
                            grasp_plan["release_lift_anchor_pos_w"] = plate_anchor + np.array(
                                [grasp_plan["place_offset"][0], grasp_plan["place_offset"][1], grasp_plan["place_z"]],
                                dtype=np.float32,
                            )
                        grasp_phase = "release_lift"
                        grasp_phase_steps = 0
                    elif grasp_phase_steps >= grasp_plan["release_steps"]:
                        now = time.monotonic()
                        if now - last_grasp_wait_report > 1.0:
                            print(
                                "[ARM] waiting for hand open before retreat: "
                                f"cmd_err={hand_err:.3f} tol={grasp_plan['hand_complete_tolerance']:.3f}"
                            )
                            last_grasp_wait_report = now
                        grasp_phase_steps = grasp_plan["release_steps"]
                elif grasp_phase == "release_lift" and (
                    phase_dist <= grasp_plan["tolerance"] or grasp_phase_steps >= grasp_plan["release_lift_steps"]
                ):
                    if current_tcp_pose is not None:
                        grasp_plan["release_retreat_anchor_pos_w"] = current_tcp_pose[0].copy()
                    else:
                        grasp_plan["release_retreat_anchor_pos_w"] = grasp_plan.get(
                            "release_lift_anchor_pos_w",
                            plate_anchor,
                        ) + plate_phase_offsets["release_lift"]
                    grasp_phase = "release_retreat"
                    grasp_phase_steps = 0
                elif grasp_phase == "release_retreat" and (
                    phase_dist <= grasp_plan["tolerance"] or grasp_phase_steps >= grasp_plan["retreat_steps"]
                ):
                    grasp_phase = "done"
                    grasp_phase_steps = 0
                if grasp_phase != old_phase:
                    print(f"[ARM] grasp phase {old_phase} -> {grasp_phase} dist={phase_dist:.3f}m")
                if grasp_phase == "lift":
                    carry_quat = grasp_plan.get("carry_tcp_quat_w")
                    grasp_plan["active_target_tcp_quat_w"] = carry_quat if carry_quat is not None else grasp_plan.get("target_tcp_quat_w")
                elif grasp_phase in {"move_to_plate", "place_lower", "release", "release_lift", "release_retreat", "done"}:
                    place_quat = grasp_plan.get("place_tcp_quat_w")
                    carry_quat = grasp_plan.get("carry_tcp_quat_w")
                    grasp_plan["active_target_tcp_quat_w"] = (
                        place_quat if place_quat is not None else carry_quat if carry_quat is not None else grasp_plan.get("target_tcp_quat_w")
                    )
                else:
                    grasp_plan["active_target_tcp_quat_w"] = grasp_plan.get("target_tcp_quat_w")
                if grasp_phase in {"release_lift", "release_retreat"}:
                    phase_anchor_key = f"{grasp_phase}_anchor_pos_w"
                    target_block_pos_w = grasp_plan.get(phase_anchor_key, plate_anchor)
                    reach_offset = plate_phase_offsets[grasp_phase]
                elif grasp_phase in plate_phase_offsets:
                    target_block_pos_w = plate_anchor
                    reach_offset = plate_phase_offsets[grasp_phase]
                else:
                    target_block_pos_w = block_anchor
                    reach_offset = block_phase_offsets.get(grasp_phase, block_phase_offsets["approach"])
                grasp_plan["active_anchor_pos_w"] = target_block_pos_w.copy()
                hand_target = CLOSE_RIGHT_HAND.copy() if grasp_phase in {"close", "lift", "move_to_plate", "place_lower"} else OPEN_RIGHT_HAND.copy()
                if grasp_phase == "done":
                    arm_mode = "hold"
                    hold_action = commanded_action.copy()
                    commanded_action = hold_action.copy()
                    desired_action = hold_action.copy()
                    hand_target = OPEN_RIGHT_HAND.copy()
                    print("[ARM] grasp-place sequence done; released cylinder, lifted vertically, and retreated.")
            if (
                arm_mode in {"reach-block", "grasp-block"}
                and reach_controller is not None
                and reach_block is not None
            ):
                target_block_pos_w = None
                target_pose_quat_w = None
                if arm_mode == "grasp-block" and grasp_plan is not None:
                    target_block_pos_w = grasp_plan.get("active_anchor_pos_w", grasp_plan.get("anchor_block_pos_w"))
                    target_pose_quat_w = grasp_plan.get("active_target_tcp_quat_w", grasp_plan.get("target_tcp_quat_w"))
                desired_action, reach_debug, reach_q_target, reach_q_current = reach_controller.update_action(
                    desired_action,
                    scene[reach_block],
                    reach_offset,
                    reach_tcp_offset,
                    hand_target,
                    offset_frame=(
                        "world"
                        if arm_mode == "grasp-block" and grasp_phase in {"release_lift", "release_retreat"}
                        else reach_offset_frame
                    ),
                    target_block_pos_w=target_block_pos_w,
                    target_tcp_quat_w=target_pose_quat_w,
                )
                target_pos = reach_debug.target_tcp_pos
                target_tcp_pos = reach_debug.target_tcp_pos
                target_tcp_quat = reach_debug.target_tcp_quat
                if reach_debug.held_for_safety:
                    now = time.monotonic()
                    if now - last_unstable_report > 1.0:
                        print(f"[WARN] reach held for safety: {reach_debug.safety_reason}")
                        last_unstable_report = now
            elif arm_mode == "test-right-arm" and test_right_arm is not None:
                desired_action[ACTION_SLICES.right_arm] = test_right_arm
                desired_action[ACTION_SLICES.right_hand] = hand_target
            if hand_target is not None and arm_mode != "idle":
                desired_action[ACTION_SLICES.right_hand] = hand_target

            next_commanded_action = smooth_command(
                commanded_action,
                desired_action,
                alpha=float(args_cli.target_alpha),
                max_joint_step=float(args_cli.max_joint_step),
            )
            hand_delta = np.clip(
                next_commanded_action[ACTION_SLICES.right_hand] - commanded_action[ACTION_SLICES.right_hand],
                -float(args_cli.hand_max_joint_step),
                float(args_cli.hand_max_joint_step),
            )
            next_commanded_action[ACTION_SLICES.right_hand] = commanded_action[ACTION_SLICES.right_hand] + hand_delta
            commanded_action = next_commanded_action
            if arm_mode == "idle":
                full_command_target = default_target.copy()
            else:
                full_command_target = default_target.copy()
                right_arm_drive_target = commanded_action[ACTION_SLICES.right_arm]
                set_named_joint_targets(
                    full_command_target,
                    robot,
                    RIGHT_ARM_JOINTS,
                    right_arm_drive_target,
                )
                set_named_joint_targets(
                    full_command_target,
                    robot,
                    RIGHT_HAND_JOINTS,
                    commanded_action[ACTION_SLICES.right_hand],
                )
            if reset_unstable_arm_state(
                robot,
                RIGHT_ARM_JOINTS,
                full_command_target,
                threshold_rad=float(args_cli.unstable_arm_threshold),
                velocity_threshold_rad_s=float(args_cli.unstable_arm_velocity_threshold),
            ):
                now = time.monotonic()
                if now - last_unstable_report > 1.0:
                    print("[WARN] right arm joint state became unstable; reset right-arm state to clamped target.")
                    last_unstable_report = now
            robot.set_joint_position_target(torch.tensor(full_command_target, device=sim.device).view(1, -1))
            last_gravity_comp_stats = apply_gravity_compensation(
                robot,
                gravity_comp_joint_ids,
                scale=float(args_cli.gravity_comp_scale),
                enabled=bool(args_cli.gravity_compensation),
            )
            robot.write_data_to_sim()
            sim.step(render=not args_cli.headless)
            robot.update(dt=sim_dt)
            for key in TASK_OBJECT_KEYS:
                scene[key].update(dt=sim_dt)
            camera.update(dt=sim_dt)
            if recording_episode is not None:
                wall_elapsed = time.monotonic() - record_wall_start if record_wall_start is not None else 0.0
                record_timeout_s = max(float(args_cli.record_episode_timeout_s), 1.0)
                if wall_elapsed >= record_timeout_s:
                    print(
                        f"[RECORD][TIMEOUT] discarded episode attempt for index {recorded_episodes}: "
                        f"wall_seconds={wall_elapsed:.1f}s timeout={record_timeout_s:.1f}s "
                        f"frames={len(recording_episode)} sim_steps={record_step}. Resetting and retrying."
                    )
                    recording_episode = None
                    record_wall_start = None
                    record_step = 0
                    default_target = reset_scene(scene, cfg, sim)
                    blue_offset_xy = sample_blue_xy_offset(rng, randomize_blue_xy)
                    blue_randomized = apply_blue_xy_offset(scene, cfg, sim, blue_offset_xy)
                    if randomize_blue_xy > 0.0:
                        blue_pos = blue_randomized["blue"]
                        print(
                            f"[RANDOMIZE] blue xy offset=({blue_offset_xy[0]:+.4f},{blue_offset_xy[1]:+.4f}) "
                            f"blue=({blue_pos[0]:.3f},{blue_pos[1]:.3f},{blue_pos[2]:.3f})"
                        )
                    reset_camera(camera, sim, cfg)
                    settle_scene_to_target(scene, camera, default_target, sim, args_cli.reset_settle_steps)
                    full_command_target = default_target.copy()
                    action = control_action_from_sim(robot)
                    commanded_action = action.copy()
                    hold_action = action.copy()
                    action_target_bias = control_action_bias_from_target(full_command_target, robot)
                    arm_mode = "idle"
                    reach_block = None
                    target_tcp_pos = None
                    target_tcp_quat = None
                    grasp_plan = None
                    grasp_phase = None
                    grasp_phase_steps = 0
                    hand_target = OPEN_RIGHT_HAND.copy()
                    auto_grasp_pending = True
                    continue
                if record_step % record_every_n == 0:
                    append_record_frame(
                        recording_episode,
                        scene,
                        robot,
                        camera,
                        commanded_action,
                        reach_controller,
                        reach_tcp_offset,
                    )
                record_step += 1
                if arm_mode == "hold" and grasp_phase == "done":
                    demo_name = writer.write_episode(recording_episode) if writer is not None else "demo"
                    sim_seconds = record_step * sim_dt
                    wall_seconds = time.monotonic() - record_wall_start if record_wall_start is not None else float("nan")
                    realtime_factor = sim_seconds / wall_seconds if wall_seconds > 1e-6 else float("nan")
                    print(
                        f"[RECORD] wrote {demo_name}: {len(recording_episode)} frames "
                        f"sim_steps={record_step} sim_seconds={sim_seconds:.2f}s "
                        f"wall_seconds={wall_seconds:.2f}s realtime_factor={realtime_factor:.2f}x"
                    )
                    recording_episode = None
                    record_wall_start = None
                    recorded_episodes += 1
                    if writer is not None and recorded_episodes >= max_record_episodes:
                        break
                    default_target = reset_scene(scene, cfg, sim)
                    blue_offset_xy = sample_blue_xy_offset(rng, randomize_blue_xy)
                    blue_randomized = apply_blue_xy_offset(scene, cfg, sim, blue_offset_xy)
                    if randomize_blue_xy > 0.0:
                        blue_pos = blue_randomized["blue"]
                        print(
                            f"[RANDOMIZE] blue xy offset=({blue_offset_xy[0]:+.4f},{blue_offset_xy[1]:+.4f}) "
                            f"blue=({blue_pos[0]:.3f},{blue_pos[1]:.3f},{blue_pos[2]:.3f})"
                        )
                    reset_camera(camera, sim, cfg)
                    settle_scene_to_target(scene, camera, default_target, sim, args_cli.reset_settle_steps)
                    full_command_target = default_target.copy()
                    action = control_action_from_sim(robot)
                    commanded_action = action.copy()
                    hold_action = action.copy()
                    arm_mode = "idle"
                    reach_block = None
                    grasp_plan = None
                    grasp_phase = None
                    grasp_phase_steps = 0
                    hand_target = OPEN_RIGHT_HAND.copy()
                    auto_grasp_pending = True
            if tcp_visualizer is not None:
                hand_tcp_pose = estimate_right_hand_tcp_pose(robot, reach_controller, reach_tcp_offset)
                if target_tcp_pos is None and reach_block is not None:
                    block_pos = scene[reach_block].data.root_pos_w[0].detach().cpu().numpy()
                    target_tcp_pos = block_pos + reach_offset
                tcp_visualizer.visualize(hand_tcp_pose, target_tcp_pos, target_tcp_quat)

            now = time.monotonic()
            if args_cli.verbose_status and now - last_report > 2.0:
                red_pos = scene["red"].data.root_pos_w[0].detach().cpu().numpy()
                blue_pos = scene["blue"].data.root_pos_w[0].detach().cpu().numpy()
                plate_pos = scene["plate"].data.root_pos_w[0].detach().cpu().numpy()
                status = (
                    f"red=({red_pos[0]:.3f},{red_pos[1]:.3f},{red_pos[2]:.3f}) "
                    f"blue=({blue_pos[0]:.3f},{blue_pos[1]:.3f},{blue_pos[2]:.3f}) "
                    f"plate=({plate_pos[0]:.3f},{plate_pos[1]:.3f},{plate_pos[2]:.3f})"
                )
                if arm_mode == "grasp-block" and grasp_phase is not None:
                    status += f" grasp_phase={grasp_phase}[{grasp_phase_steps}]"
                if reach_debug is not None:
                    status += (
                        f" block=({reach_debug.block_pos[0]:.3f},{reach_debug.block_pos[1]:.3f},{reach_debug.block_pos[2]:.3f}) "
                        f"offset_frame={reach_debug.offset_frame} "
                        f"offset_w=({reach_debug.offset_world[0]:.3f},{reach_debug.offset_world[1]:.3f},{reach_debug.offset_world[2]:.3f}) "
                        f"target_tcp=({reach_debug.target_tcp_pos[0]:.3f},{reach_debug.target_tcp_pos[1]:.3f},{reach_debug.target_tcp_pos[2]:.3f}) "
                        f"tcp=({reach_debug.current_tcp_pos[0]:.3f},{reach_debug.current_tcp_pos[1]:.3f},{reach_debug.current_tcp_pos[2]:.3f}) "
                        f"tcp_err=({reach_debug.tcp_error[0]:.3f},{reach_debug.tcp_error[1]:.3f},{reach_debug.tcp_error[2]:.3f}) "
                        f"rot_err=({reach_debug.rot_error_axis_angle[0]:.3f},{reach_debug.rot_error_axis_angle[1]:.3f},{reach_debug.rot_error_axis_angle[2]:.3f}) "
                        f"step_w=({reach_debug.step_error_world[0]:.4f},{reach_debug.step_error_world[1]:.4f},{reach_debug.step_error_world[2]:.4f}) "
                        f"pred_w=({reach_debug.predicted_tcp_delta[0]:.4f},{reach_debug.predicted_tcp_delta[1]:.4f},{reach_debug.predicted_tcp_delta[2]:.4f}) "
                        f"actual_d=({reach_debug.actual_delta_world[0]:.4f},{reach_debug.actual_delta_world[1]:.4f},{reach_debug.actual_delta_world[2]:.4f}) "
                        f"dq=({','.join(f'{x:+.4f}' for x in reach_debug.joint_delta)}) "
                        f"jac_row={reach_debug.jacobian_body_row} "
                        f"jac_sign={reach_debug.jacobian_sign:.1f} "
                        f"dir_sign={reach_debug.direction_sign:.1f} "
                        f"progress={reach_debug.actual_progress:.5f} "
                        f"right_tcp_dist={reach_debug.tcp_dist:.3f}m"
                    )
                    if reach_debug.held_for_safety:
                        status += f" reach_held={reach_debug.safety_reason}"
                if reach_q_target is not None and reach_q_current is not None:
                    q_err = float(np.max(np.abs(reach_q_target - reach_q_current)))
                    q_lag = float(np.max(np.abs(reach_q_target - commanded_action[ACTION_SLICES.right_arm])))
                    cmd_delta = commanded_action[ACTION_SLICES.right_arm] - reach_q_current
                    drive_delta = (
                        commanded_action[ACTION_SLICES.right_arm]
                        + action_target_bias[ACTION_SLICES.right_arm]
                        - reach_q_current
                    )
                    status += (
                        f" right_arm_q_err={q_err:.3f} right_arm_cmd_lag={q_lag:.3f} "
                        f"cmd_delta=({','.join(f'{x:+.4f}' for x in cmd_delta)}) "
                        f"drive_delta=({','.join(f'{x:+.4f}' for x in drive_delta)})"
                    )
                if args_cli.gravity_compensation:
                    status += (
                        f" gravity_comp=max:{last_gravity_comp_stats[0]:.2f}"
                        f"/mean:{last_gravity_comp_stats[1]:.2f}"
                    )
                if arm_mode == "test-right-arm" and test_right_arm is not None:
                    q_lag = float(np.max(np.abs(test_right_arm - commanded_action[ACTION_SLICES.right_arm])))
                    status += f" direct_right_arm_cmd_lag={q_lag:.3f}"
                print(status)
                last_report = now
    finally:
        if keyboard_jog is not None:
            keyboard_jog.stop()
        if writer is not None:
            writer.close()


def main() -> None:
    cfg = make_scene_cfg()
    if args_cli.print_layout:
        print(format_action_layout())
        print(format_layout(cfg))

    sim = create_simulation_context(args_cli.device)
    scene = build_scene(cfg)
    sim.reset()
    reset_camera(scene["camera"], sim, cfg)
    run_debug(scene, cfg, sim)


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
