#!/usr/bin/env python
"""Run a trained SmolVLA policy in the active IsaacLab task scene."""

from __future__ import annotations

import argparse
import base64
import csv
import importlib
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PROJECT_DIR_FOR_DEFAULTS = Path(__file__).resolve().parents[1]

from isaaclab.app import AppLauncher


parser = argparse.ArgumentParser(description="Evaluate the active task's SmolVLA checkpoint in IsaacLab.")
parser.add_argument("--checkpoint", default=None, help="Checkpoint, pretrained_model, or training output directory.")
parser.add_argument("--dataset-root", type=Path, default=None, help="Converted LeRobot dataset. Defaults to the active task dataset.")
parser.add_argument("--steps", type=int, default=0, help="Physics steps. 0 runs exactly one dataset-derived phase schedule.")
parser.add_argument("--phase-duration-scale", type=float, default=1.0)
parser.add_argument("--policy-every-n-steps", type=int, default=0, help="0 derives the interval from simulation and dataset FPS.")
parser.add_argument("--video-every-n-steps", type=int, default=6)
parser.add_argument("--output-video", type=Path, default=PROJECT_DIR_FOR_DEFAULTS / "outputs/eval/smolvla_drawer_rollout.avi")
parser.add_argument("--video-layout", choices=["chest", "all"], default="all")
parser.add_argument("--policy-python", default="/home/zfy/miniconda3/envs/smolvla/bin/python")
parser.add_argument("--policy-device", choices=["cuda", "cpu"], default="cuda")
parser.add_argument("--policy-startup-timeout", type=float, default=180.0)
parser.add_argument("--policy-request-timeout", type=float, default=60.0)
parser.add_argument("--action-clip", choices=["none", "dataset_minmax", "dataset_q01_q99"], default="dataset_minmax")
parser.add_argument("--chunk-replan-frames", type=int, default=25, help="Predict a new overlapping action chunk every N policy frames.")
parser.add_argument("--chunk-overlap-blend-frames", type=int, default=5, help="Cross-fade only the previous and newest stochastic chunks for N frames.")
parser.add_argument("--phase-transition-blend-frames", type=int, default=8)
parser.add_argument("--phase-state-gating", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--phase-max-extension-frames", type=int, default=20)
parser.add_argument("--phase-q-track-tolerance", type=float, default=0.08)
parser.add_argument("--phase-hand-tolerance", type=float, default=0.15)
parser.add_argument("--phase-hand-close-min-progress", type=float, default=0.10)
parser.add_argument("--diagnostics-csv", type=Path, default=None)
parser.add_argument("--diagnostics-plot", type=Path, default=None)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--randomize-task", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--camera-width", type=int, default=680)
parser.add_argument("--camera-height", type=int, default=480)
parser.add_argument("--robot-base-z", type=float, default=0.98)
parser.add_argument("--joint-stiffness", type=float, default=600.0)
parser.add_argument("--joint-damping", type=float, default=80.0)
parser.add_argument("--joint-effort-limit", type=float, default=300.0)
parser.add_argument(
    "--target-alpha",
    type=float,
    default=0.32,
    help="Deprecated compatibility option; rollout now uses fixed 20 Hz linear interpolation.",
)
parser.add_argument("--max-joint-step", type=float, default=0.050)
parser.add_argument("--hand-max-joint-step", type=float, default=0.015)
parser.add_argument("--reset-settle-s", type=float, default=2.0)
parser.add_argument("--gravity-compensation", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--gravity-comp-scale", type=float, default=1.0)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import cv2
import numpy as np
import torch

from s4_pipeline.config import load_project_config
from s4_robot.control_mapping import (
    ACTION_SLICES,
    BIMANUAL_ARM_HAND_JOINTS,
    extract_bimanual_state,
    make_full_joint_target,
)
from s4_robot.s4_robot_cfg import ALL_DRIVE_JOINTS, get_default_joint_positions
from s4_robot.simulation import (
    SceneBuildCfg,
    create_simulation_context,
    reset_camera,
    write_object_pose,
)
from tasks import get_task_spec
from tasks.drawer_insert_close_controller import DEFAULT_SCRIPTED_CONFIG, load_scripted_config


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "s4_bimanual_dataset.json"
SERVER_PATH = Path(__file__).resolve().parent / "policy_server.py"
IMAGE_TO_SCENE_CAMERA = {
    "observation.images.chest_front_rgb": "chest",
    "observation.images.left_wrist_rgb": "left",
    "observation.images.right_wrist_rgb": "right",
}


def resolve_scene_builder(task_id: str):
    spec = get_task_spec(task_id)
    module_name, function_name = spec.scene_builder.split(":", 1)
    return getattr(importlib.import_module(module_name), function_name)


def resolve_dataset_root(project_cfg) -> Path:
    if args_cli.dataset_root is not None:
        return args_cli.dataset_root.expanduser().resolve()
    return (project_cfg.dataset.lerobot_root / project_cfg.dataset.repo_id.split("/")[-1]).resolve()


def numeric_checkpoints(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((path for path in root.iterdir() if path.is_dir() and path.name.isdigit()), key=lambda path: int(path.name))


def resolve_checkpoint(project_cfg) -> Path:
    path = Path(args_cli.checkpoint).expanduser() if args_cli.checkpoint else project_cfg.training.output_dir
    if (path / "config.json").is_file():
        return path.resolve()
    if (path / "pretrained_model" / "config.json").is_file():
        return (path / "pretrained_model").resolve()
    checkpoints_root = path / "checkpoints" if (path / "checkpoints").is_dir() else path
    checkpoints = numeric_checkpoints(checkpoints_root)
    if checkpoints and (checkpoints[-1] / "pretrained_model" / "config.json").is_file():
        return (checkpoints[-1] / "pretrained_model").resolve()
    raise FileNotFoundError(f"No SmolVLA pretrained_model/config.json found from: {path}")


def make_scene_cfg(project_cfg) -> SceneBuildCfg:
    return SceneBuildCfg(
        table_top_z=float(project_cfg.scene.table_top_z),
        joint_stiffness=float(args_cli.joint_stiffness),
        joint_damping=float(args_cli.joint_damping),
        joint_effort_limit=float(args_cli.joint_effort_limit),
        scene_usd=project_cfg.scene.scene_usd,
        table_usd=project_cfg.scene.table_usd,
        robot_base_z=float(args_cli.robot_base_z),
        camera_width=max(int(args_cli.camera_width), 1),
        camera_height=max(int(args_cli.camera_height), 1),
    )


def camera_rgb_uint8(camera) -> np.ndarray:
    rgb = camera.data.output["rgb"][0].detach().cpu().numpy()
    if rgb.dtype != np.uint8:
        rgb = (np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    return rgb[..., :3].copy()


def update_scene(scene: dict[str, object], dt: float) -> None:
    scene["robot"].update(dt=dt)
    drawer = scene.get("drawer")
    if drawer is not None:
        drawer.update(dt=dt)
    for obj in scene.get("dynamic_objects", []):
        obj.update(dt=dt)
    scene["camera"].update(dt=dt)
    for camera in scene.get("wrist_cameras", {}).values():
        camera.update(dt=dt)


def current_images(scene: dict[str, object], expected_keys: list[str]) -> dict[str, np.ndarray]:
    cameras = {
        "chest": scene["camera"],
        "left": scene["wrist_cameras"]["left_wrist"],
        "right": scene["wrist_cameras"]["right_wrist"],
    }
    images: dict[str, np.ndarray] = {}
    for key in expected_keys:
        camera_name = IMAGE_TO_SCENE_CAMERA.get(key)
        if camera_name is None:
            raise KeyError(f"Checkpoint requests unsupported camera feature: {key}")
        images[key] = camera_rgb_uint8(cameras[camera_name])
    return images


def load_action_bounds(dataset_root: Path) -> tuple[np.ndarray | None, np.ndarray | None]:
    if args_cli.action_clip == "none":
        return None, None
    stats_path = dataset_root / "meta" / "stats.json"
    with stats_path.open("r", encoding="utf-8") as stream:
        stats = json.load(stream)["action"]
    keys = ("q01", "q99") if args_cli.action_clip == "dataset_q01_q99" else ("min", "max")
    low = np.asarray(stats[keys[0]], dtype=np.float32).reshape(-1)
    high = np.asarray(stats[keys[1]], dtype=np.float32).reshape(-1)
    if low.shape != (26,) or high.shape != (26,):
        raise ValueError(f"Expected 26D action bounds, got {low.shape}/{high.shape}")
    return low, high


def make_policy_server_env() -> dict[str, str]:
    env = os.environ.copy()
    prefix = Path(args_cli.policy_python).expanduser().resolve().parent.parent
    cache = PROJECT_DIR / ".cache" / "huggingface"
    env["CONDA_PREFIX"] = str(prefix)
    env["PATH"] = f"{prefix / 'bin'}:/usr/bin:/bin"
    env.pop("PYTHONPATH", None)
    env["LD_LIBRARY_PATH"] = str(prefix / "lib")
    env["HF_HOME"] = str(cache)
    env["HF_HUB_CACHE"] = str(cache / "hub")
    env["HF_DATASETS_CACHE"] = str(cache / "datasets")
    env["TRANSFORMERS_CACHE"] = str(cache / "transformers")
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("HUGGINGFACE_HUB_OFFLINE", "1")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    return env


class PolicyServer:
    def __init__(self, checkpoint: Path, dataset_root: Path):
        command = [
            args_cli.policy_python,
            str(SERVER_PATH),
            "--checkpoint",
            str(checkpoint),
            "--dataset-root",
            str(dataset_root),
            "--device",
            args_cli.policy_device,
            "--seed",
            str(args_cli.seed),
        ]
        print("[EVAL] starting policy server:\n[EVAL]   " + " ".join(command), flush=True)
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
            env=make_policy_server_env(),
        )
        self.ready = self._read(float(args_cli.policy_startup_timeout), "startup")
        if self.ready.get("status") != "ready":
            self.close()
            raise RuntimeError(f"Policy server did not become ready: {self.ready}")
        self.image_keys = list(self.ready["image_keys"])
        self.phase_schedule = list(self.ready["phase_schedule"])
        if int(self.ready["state_dim"]) != 26 or int(self.ready["action_dim"]) != 26:
            self.close()
            raise ValueError(f"Drawer rollout requires checkpoint state/action=26/26, got {self.ready}")

    def _read(self, timeout: float, context: str) -> dict:
        assert self.proc.stdout is not None
        deadline = time.monotonic() + max(timeout, 0.1)
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Policy server exited during {context} with code {self.proc.returncode}")
            readable, _, _ = select.select([self.proc.stdout], [], [], min(1.0, deadline - time.monotonic()))
            if readable:
                line = self.proc.stdout.readline()
                if not line:
                    raise RuntimeError(f"Policy server closed stdout during {context}")
                return json.loads(line)
        raise TimeoutError(f"Policy server {context} timed out after {timeout:.0f}s")

    def request(self, payload: dict) -> dict:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        response = self._read(float(args_cli.policy_request_timeout), "inference")
        if "error" in response:
            raise RuntimeError(response["error"])
        return response

    def reset(self) -> None:
        self.request({"command": "reset"})

    def action_chunk(self, state: np.ndarray, images: dict[str, np.ndarray], task: str) -> np.ndarray:
        encoded = {
            key: {
                "shape": list(image.shape),
                "b64": base64.b64encode(image.tobytes()).decode("ascii"),
            }
            for key, image in images.items()
        }
        action_chunk = np.asarray(
            self.request({"state": state.tolist(), "images": encoded, "task": task, "mode": "chunk"})[
                "action_chunk"
            ],
            dtype=np.float32,
        )
        if action_chunk.ndim != 2 or action_chunk.shape[1] != 26:
            raise ValueError(f"Policy returned action chunk shape {action_chunk.shape}, expected (T, 26)")
        return action_chunk

    def close(self) -> None:
        proc = getattr(self, "proc", None)
        if proc is None or proc.poll() is not None:
            return
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.wait(timeout=5.0)
        except Exception:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()


class VideoWriter:
    def __init__(self, path: Path, fps: float, shape: tuple[int, ...]):
        path.parent.mkdir(parents=True, exist_ok=True)
        height, width = shape[:2]
        self.path = path
        self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))
        if not self.writer.isOpened():
            raise RuntimeError(f"Could not open video writer: {path}")

    def write(self, rgb: np.ndarray) -> None:
        self.writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    def close(self) -> None:
        self.writer.release()


def compose_video_frame(scene: dict[str, object], phase: dict, step: int, total_steps: int) -> np.ndarray:
    chest = camera_rgb_uint8(scene["camera"])
    if args_cli.video_layout == "all":
        left = camera_rgb_uint8(scene["wrist_cameras"]["left_wrist"])
        right = camera_rgb_uint8(scene["wrist_cameras"]["right_wrist"])
        frame = np.concatenate([chest, left, right], axis=1)
        labels = (("CHEST", 12), ("LEFT WRIST", chest.shape[1] + 12), ("RIGHT WRIST", chest.shape[1] * 2 + 12))
        for label, x in labels:
            cv2.putText(frame, label, (x, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
    else:
        frame = chest
    text = f"phase {int(phase['phase_index']) + 1:02d}: {phase['task']}"
    cv2.rectangle(frame, (0, frame.shape[0] - 58), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
    cv2.putText(frame, text[:150], (12, frame.shape[0] - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"step {step}/{total_steps}", (12, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (120, 220, 255), 1, cv2.LINE_AA)
    return frame


def reset_drawer_scene(scene: dict[str, object], cfg: SceneBuildCfg, sim, scripted_cfg: dict) -> tuple[np.ndarray, int, float, np.ndarray]:
    robot = scene["robot"]
    drawer = scene["drawer"]
    random_cfg = scripted_cfg.get("randomization", {})
    rng = np.random.default_rng(int(args_cli.seed))
    can_offset = np.zeros(2, dtype=np.float32)
    drawer_open = 0.0
    if args_cli.randomize_task:
        can_cfg = random_cfg.get("can_xy", {})
        x_range = can_cfg.get("x_range", [0.0, 0.0])
        y_range = can_cfg.get("y_range", [0.0, 0.0])
        can_offset[:] = [rng.uniform(*x_range), rng.uniform(*y_range)]
        open_range = random_cfg.get("drawer_initial_open", {}).get("range", [0.0, 0.0])
        drawer_open = float(rng.uniform(*open_range))

    sim.reset()
    defaults = get_default_joint_positions()
    robot_q = torch.zeros(1, robot.num_joints, dtype=torch.float32, device=sim.device)
    for drive_index, name in enumerate(ALL_DRIVE_JOINTS):
        if name in robot.joint_names:
            robot_q[0, robot.joint_names.index(name)] = float(defaults[drive_index])
    robot.write_joint_state_to_sim(robot_q, torch.zeros_like(robot_q))
    robot.reset()
    initial_action = extract_bimanual_state(robot_q[0].cpu().numpy(), robot.joint_names)
    hand_cfg = scripted_cfg.get("hands", {})
    initial_action[ACTION_SLICES.left_hand] = np.asarray(hand_cfg["left_open"], dtype=np.float32)
    initial_action[ACTION_SLICES.right_hand] = np.asarray(hand_cfg["right_open"], dtype=np.float32)
    full_target = make_full_joint_target(initial_action, robot.joint_names, robot_q[0].cpu().numpy(), include_mimic=True)

    drawer_cfg = random_cfg.get("drawer_initial_open", {})
    joint_name = str(drawer_cfg.get("joint_name", "drawer_top_joint"))
    joint_ids, _ = drawer.find_joints(f"^{joint_name}$")
    if len(joint_ids) != 1:
        raise RuntimeError(f"Expected one {joint_name}, found {joint_ids}")
    drawer_joint_id = int(joint_ids[0])
    sign = float(drawer_cfg.get("joint_position_sign", 1.0))
    drawer.reset()
    drawer_q = drawer.data.default_joint_pos.clone()
    drawer_qd = drawer.data.default_joint_vel.clone()
    drawer_q[:, drawer_joint_id] = sign * drawer_open
    drawer_qd.zero_()
    drawer.write_joint_state_to_sim(drawer_q, drawer_qd)

    can_obj = scene["named_objects"]["can"]
    for obj, position, quat in scene.get("object_initial_poses", []):
        object_position = np.asarray(position, dtype=np.float32).copy()
        if obj is can_obj:
            object_position[:2] += can_offset
        write_object_pose(obj, object_position, sim.device, quat)

    reset_camera(scene["camera"], sim, cfg)
    target_tensor = torch.tensor(full_target, dtype=torch.float32, device=robot.device).view(1, -1)
    settle_steps = int(round(max(float(args_cli.reset_settle_s), 0.0) / sim.get_physics_dt()))
    for _ in range(settle_steps):
        robot.set_joint_position_target(target_tensor)
        robot.write_data_to_sim()
        sim.step(render=True)
        update_scene(scene, sim.get_physics_dt())
    actual = robot.data.joint_pos[0].detach().cpu().numpy()
    full_target = actual.copy()
    initial_action = extract_bimanual_state(actual, robot.joint_names)
    print(f"[EVAL] reset can_xy_offset=({can_offset[0]:+.3f},{can_offset[1]:+.3f}) drawer_open={drawer_open:.3f}m")
    return full_target, drawer_joint_id, sign, initial_action


def apply_gravity_compensation(robot, joint_ids: list[int]) -> None:
    if not args_cli.gravity_compensation:
        return
    gravity = robot.root_physx_view.get_gravity_compensation_forces()
    if gravity.shape[1] > max(joint_ids):
        robot.set_joint_effort_target(gravity[:, joint_ids] * float(args_cli.gravity_comp_scale), joint_ids=joint_ids)


def print_schedule(schedule: list[dict], policy_interval: int, fps: int) -> None:
    print(f"[EVAL] dataset phase schedule ({len(schedule)} phases, {sum(p['frames'] for p in schedule)} frames at {fps}Hz):")
    for phase in schedule:
        seconds = phase["frames"] / max(fps, 1)
        print(
            f"[EVAL]   {phase['phase_index'] + 1:02d}. {phase['frames']:3d} frames"
            f" ({seconds:4.1f}s) {phase['task']}"
        )
    print(f"[EVAL] policy interval={policy_interval} sim steps")


def ensemble_action(
    chunks: list[dict[str, object]],
    policy_frame: int,
    blend_frames: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    candidates: list[tuple[int, np.ndarray]] = []
    for item in chunks:
        start = int(item["start"])
        chunk = np.asarray(item["actions"], dtype=np.float32)
        offset = policy_frame - start
        if 0 <= offset < len(chunk):
            candidates.append((start, chunk[offset]))
    if not candidates:
        raise RuntimeError(f"No action chunk covers policy frame {policy_frame}")
    candidates.sort(key=lambda item: item[0])
    candidates = candidates[-2:]
    newest_start, newest = candidates[-1]
    if len(candidates) == 1 or blend_frames <= 0:
        return newest.copy(), newest.copy(), len(candidates)
    previous = candidates[-2][1]
    blend = min(float(policy_frame - newest_start + 1) / float(blend_frames), 1.0)
    combined = (1.0 - blend) * previous + blend * newest
    return newest.copy(), combined.astype(np.float32), len(candidates)


def phase_transition_gate(
    phase: dict[str, object],
    scripted_cfg: dict,
    actual_action: np.ndarray,
    commanded_action: np.ndarray,
    drawer_open: float,
) -> tuple[bool, list[str]]:
    if not args_cli.phase_state_gating:
        return True, []
    reasons: list[str] = []
    for side, action_slice in (("left", ACTION_SLICES.left_arm), ("right", ACTION_SLICES.right_arm)):
        arm_error = float(np.max(np.abs(commanded_action[action_slice] - actual_action[action_slice])))
        if arm_error > float(args_cli.phase_q_track_tolerance):
            reasons.append(f"{side}_arm={arm_error:.3f}")

    phase_cfg = next(
        (item for item in scripted_cfg.get("phases", []) if str(item.get("task")) == str(phase["task"])),
        {},
    )
    hands_cfg = scripted_cfg.get("hands", {})
    for side, action_slice in (("left", ACTION_SLICES.left_hand), ("right", ACTION_SLICES.right_hand)):
        hand_command = phase_cfg.get(f"{side}_hand")
        if not isinstance(hand_command, str) or hand_command not in {"open", "close"}:
            continue
        # A grasping hand is expected to stop against the object before reaching
        # its free-space close target. Require evidence that closure started,
        # rather than requiring the fingers to pass through the grasped object.
        if hand_command == "close":
            open_target = np.asarray(hands_cfg[f"{side}_open"], dtype=np.float32)
            close_target = np.asarray(hands_cfg[f"{side}_close"], dtype=np.float32)
            direction = close_target - open_target
            valid = np.abs(direction) > 1.0e-4
            progress = np.zeros_like(direction)
            progress[valid] = (actual_action[action_slice][valid] - open_target[valid]) / direction[valid]
            close_progress = float(np.median(np.clip(progress[valid], 0.0, 1.0)))
            minimum = float(args_cli.phase_hand_close_min_progress)
            if close_progress < minimum:
                reasons.append(f"{side}_close={close_progress:.2f}<{minimum:.2f}")
            continue
        target = np.asarray(hands_cfg[f"{side}_{hand_command}"], dtype=np.float32)
        error = float(np.max(np.abs(actual_action[action_slice] - target)))
        if error > float(args_cli.phase_hand_tolerance):
            reasons.append(f"{side}_hand={error:.3f}")

    if phase_cfg.get("drawer_open_min") is not None:
        minimum = float(phase_cfg["drawer_open_min"])
        if drawer_open < minimum:
            reasons.append(f"drawer={drawer_open:.3f}<{minimum:.3f}")
    if phase_cfg.get("drawer_open_max") is not None:
        maximum = float(phase_cfg["drawer_open_max"])
        if drawer_open > maximum:
            reasons.append(f"drawer={drawer_open:.3f}>{maximum:.3f}")
    if phase_cfg.get("close_drawer_from_current"):
        close_limit = float(scripted_cfg.get("success", {}).get("drawer_open_abs_max", 0.04))
        if abs(drawer_open) >= close_limit:
            reasons.append(f"drawer_abs={abs(drawer_open):.3f}>={close_limit:.3f}")
    return not reasons, reasons


def diagnostics_paths() -> tuple[Path, Path]:
    csv_path = args_cli.diagnostics_csv or args_cli.output_video.with_name(
        f"{args_cli.output_video.stem}_actions.csv"
    )
    plot_path = args_cli.diagnostics_plot or args_cli.output_video.with_name(
        f"{args_cli.output_video.stem}_actions.png"
    )
    return csv_path, plot_path


def write_action_diagnostics(rows: list[dict[str, object]]) -> tuple[Path, Path] | None:
    if not rows:
        return None
    csv_path, plot_path = diagnostics_paths()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    scalar_fields = [
        "policy_frame",
        "sim_step",
        "phase_index",
        "phase_frame",
        "chunk_count",
        "drawer_open_m",
    ]
    vector_fields = ("raw", "ensemble", "command", "actual")
    header = scalar_fields + [
        f"{prefix}.{joint_name}"
        for prefix in vector_fields
        for joint_name in BIMANUAL_ARM_HAND_JOINTS
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        for row in rows:
            values = [row[field] for field in scalar_fields]
            for prefix in vector_fields:
                values.extend(np.asarray(row[prefix], dtype=np.float32).tolist())
            writer.writerow(values)

    raw = np.stack([np.asarray(row["raw"], dtype=np.float32) for row in rows])
    ensemble = np.stack([np.asarray(row["ensemble"], dtype=np.float32) for row in rows])
    command = np.stack([np.asarray(row["command"], dtype=np.float32) for row in rows])
    actual = np.stack([np.asarray(row["actual"], dtype=np.float32) for row in rows])
    groups = {
        "LA": ACTION_SLICES.left_arm,
        "LH": ACTION_SLICES.left_hand,
        "RA": ACTION_SLICES.right_arm,
        "RH": ACTION_SLICES.right_hand,
    }
    for name, group_slice in groups.items():
        if len(rows) > 1:
            raw_jump = np.max(np.abs(np.diff(raw[:, group_slice], axis=0)), axis=1)
            fused_jump = np.max(np.abs(np.diff(ensemble[:, group_slice], axis=0)), axis=1)
        else:
            raw_jump = np.zeros(1, dtype=np.float32)
            fused_jump = np.zeros(1, dtype=np.float32)
        tracking = np.max(np.abs(command[:, group_slice] - actual[:, group_slice]), axis=1)
        print(
            f"[DIAG] {name} raw_jump(mean/p95)={np.mean(raw_jump):.4f}/{np.quantile(raw_jump, 0.95):.4f} "
            f"fused_jump={np.mean(fused_jump):.4f}/{np.quantile(fused_jump, 0.95):.4f} "
            f"tracking={np.mean(tracking):.4f}/{np.quantile(tracking, 0.95):.4f}rad"
        )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        x = np.asarray([int(row["policy_frame"]) for row in rows])
        fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
        for name, group_slice in groups.items():
            raw_jump = np.r_[0.0, np.max(np.abs(np.diff(raw[:, group_slice], axis=0)), axis=1)]
            axes[0].plot(x, raw_jump, label=name)
            axes[1].plot(x, np.max(np.abs(raw[:, group_slice] - ensemble[:, group_slice]), axis=1), label=name)
            axes[2].plot(x, np.max(np.abs(command[:, group_slice] - actual[:, group_slice]), axis=1), label=name)
        axes[0].set_ylabel("raw jump [rad]")
        axes[1].set_ylabel("smoothing correction [rad]")
        axes[2].set_ylabel("tracking error [rad]")
        axes[2].set_xlabel("policy frame (20 Hz)")
        for axis in axes:
            axis.grid(True, alpha=0.3)
            axis.legend(ncol=4)
        fig.tight_layout()
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(plot_path, dpi=140)
        plt.close(fig)
    except Exception as exc:
        print(f"[WARN] could not write diagnostics plot: {type(exc).__name__}: {exc}")
    return csv_path, plot_path


def main() -> None:
    project_cfg = load_project_config(CONFIG_PATH)
    task_spec = get_task_spec(project_cfg.dataset.task_id)
    if task_spec.data.state_dim != 26 or task_spec.data.action_dim != 26:
        raise ValueError(f"This rollout currently requires a 26D bimanual task, got {task_spec.data}")
    dataset_root = resolve_dataset_root(project_cfg)
    checkpoint = resolve_checkpoint(project_cfg)
    action_low, action_high = load_action_bounds(dataset_root)
    scripted_cfg = load_scripted_config(DEFAULT_SCRIPTED_CONFIG)

    sim = create_simulation_context(args_cli.device)
    cfg = make_scene_cfg(project_cfg)
    scene_builder = resolve_scene_builder(project_cfg.dataset.task_id)
    print(f"[BOOT] scene builder: {scene_builder.__module__}:{scene_builder.__name__}")
    scene = scene_builder(cfg)
    sim.reset()
    robot = scene["robot"]
    camera = scene["camera"]
    sim_dt = sim.get_physics_dt()

    server = PolicyServer(checkpoint, dataset_root)
    expected_camera_keys = set(IMAGE_TO_SCENE_CAMERA)
    if set(server.image_keys) != expected_camera_keys:
        server.close()
        raise ValueError(f"Checkpoint cameras={server.image_keys}, expected={sorted(expected_camera_keys)}")
    policy_interval = int(args_cli.policy_every_n_steps)
    if policy_interval <= 0:
        policy_interval = max(int(round(1.0 / (sim_dt * project_cfg.dataset.fps))), 1)
    schedule = []
    for phase in server.phase_schedule:
        item = dict(phase)
        item["frames"] = max(
            int(round(item["frames"] * max(float(args_cli.phase_duration_scale), 0.05))),
            1,
        )
        schedule.append(item)
    scheduled_policy_frames = sum(phase["frames"] for phase in schedule)
    extension_budget = max(int(args_cli.phase_max_extension_frames), 0) * max(len(schedule) - 1, 0)
    scheduled_steps = scheduled_policy_frames * policy_interval
    total_steps = (
        int(args_cli.steps)
        if int(args_cli.steps) > 0
        else (scheduled_policy_frames + extension_budget) * policy_interval
    )
    print(f"[EVAL] checkpoint={checkpoint}")
    print(f"[EVAL] dataset={dataset_root}")
    print_schedule(schedule, policy_interval, project_cfg.dataset.fps)
    print(
        f"[EVAL] rollout scheduled_steps={scheduled_steps} hard_limit_steps={total_steps} "
        f"scheduled_seconds={scheduled_steps * sim_dt:.1f}"
    )
    print(
        f"[EVAL] chunk overlap replan={max(int(args_cli.chunk_replan_frames), 1)} frames "
        f"overlap_blend={max(int(args_cli.chunk_overlap_blend_frames), 0)} frames "
        f"phase_blend={max(int(args_cli.phase_transition_blend_frames), 0)} frames"
    )

    full_target, drawer_joint_id, drawer_sign, commanded_action = reset_drawer_scene(scene, cfg, sim, scripted_cfg)
    gravity_joint_ids = [robot.joint_names.index(name) for name in ALL_DRIVE_JOINTS if name in robot.joint_names]
    writer: VideoWriter | None = None
    phase_index = 0
    phase_frame = 0
    phase_extension = 0
    policy_frame = 0
    chunks: list[dict[str, object]] = []
    interpolation_start = commanded_action.copy()
    interpolation_goal = commanded_action.copy()
    transition_from_action = commanded_action.copy()
    diagnostics: list[dict[str, object]] = []
    actual_steps = 0
    rollout_complete = False
    server.reset()
    start = time.monotonic()

    try:
        for step in range(max(total_steps, 1)):
            if step % policy_interval == 0:
                actual_action = extract_bimanual_state(
                    robot.data.joint_pos[0].detach().cpu().numpy(), robot.joint_names
                )
                # Align the previous 20 Hz command endpoint with the measured
                # state after its six 120 Hz interpolation steps have executed.
                if diagnostics:
                    diagnostics[-1]["actual"] = actual_action.copy()
                drawer_open = drawer_sign * float(
                    scene["drawer"].data.joint_pos[0, drawer_joint_id].item()
                )
                if phase_frame >= schedule[phase_index]["frames"]:
                    gate_ready, gate_reasons = phase_transition_gate(
                        schedule[phase_index],
                        scripted_cfg,
                        actual_action,
                        commanded_action,
                        drawer_open,
                    )
                    extension_limit = max(int(args_cli.phase_max_extension_frames), 0)
                    force_transition = phase_extension >= extension_limit
                    if gate_ready or force_transition:
                        if not gate_ready:
                            print(
                                f"[EVAL][GATE] phase {phase_index + 1:02d} forced after "
                                f"{phase_extension} extension frames: {', '.join(gate_reasons)}"
                            )
                        if phase_index == len(schedule) - 1:
                            rollout_complete = True
                            break
                        transition_from_action = commanded_action.copy()
                        phase_index += 1
                        phase_frame = 0
                        phase_extension = 0
                        chunks.clear()
                        server.reset()
                        print(
                            f"[EVAL] phase -> {phase_index + 1:02d}/{len(schedule)} "
                            f"{schedule[phase_index]['task']}"
                        )
                    else:
                        phase_extension += 1
                        if phase_extension == 1 or phase_extension % 5 == 0:
                            print(
                                f"[EVAL][GATE] holding phase {phase_index + 1:02d} "
                                f"extension={phase_extension}/{extension_limit}: {', '.join(gate_reasons)}"
                            )
                phase = schedule[phase_index]
                replan_frames = max(int(args_cli.chunk_replan_frames), 1)
                if not chunks or phase_frame % replan_frames == 0:
                    images = current_images(scene, server.image_keys)
                    chunk = server.action_chunk(actual_action, images, phase["task"])
                    chunks.append({"start": policy_frame, "actions": chunk})
                chunks = [
                    item
                    for item in chunks
                    if policy_frame - int(item["start"]) < len(np.asarray(item["actions"]))
                ][-2:]
                raw_action, ensemble_target, chunk_count = ensemble_action(
                    chunks,
                    policy_frame,
                    max(int(args_cli.chunk_overlap_blend_frames), 0),
                )
                if action_low is not None and action_high is not None:
                    raw_action = np.clip(raw_action, action_low, action_high)
                    ensemble_target = np.clip(ensemble_target, action_low, action_high)

                blend_frames = max(int(args_cli.phase_transition_blend_frames), 0)
                if blend_frames > 0 and phase_frame < blend_frames:
                    blend = float(phase_frame + 1) / float(blend_frames)
                    ensemble_target = (1.0 - blend) * transition_from_action + blend * ensemble_target

                interpolation_start = commanded_action.copy()
                goal_delta = ensemble_target - interpolation_start
                arm_limit = float(args_cli.max_joint_step) * policy_interval
                hand_limit = float(args_cli.hand_max_joint_step) * policy_interval
                for arm_slice in (ACTION_SLICES.left_arm, ACTION_SLICES.right_arm):
                    goal_delta[arm_slice] = np.clip(goal_delta[arm_slice], -arm_limit, arm_limit)
                for hand_slice in (ACTION_SLICES.left_hand, ACTION_SLICES.right_hand):
                    goal_delta[hand_slice] = np.clip(goal_delta[hand_slice], -hand_limit, hand_limit)
                interpolation_goal = (interpolation_start + goal_delta).astype(np.float32)

                diagnostics.append(
                    {
                        "policy_frame": policy_frame,
                        "sim_step": step,
                        "phase_index": phase_index,
                        "phase_frame": phase_frame,
                        "chunk_count": chunk_count,
                        "drawer_open_m": drawer_open,
                        "raw": raw_action.copy(),
                        "ensemble": ensemble_target.copy(),
                        "command": interpolation_goal.copy(),
                        "actual": actual_action.copy(),
                    }
                )
                phase_frame += 1
                policy_frame += 1

            interpolation_fraction = float(step % policy_interval + 1) / float(policy_interval)
            commanded_action = (
                interpolation_start
                + interpolation_fraction * (interpolation_goal - interpolation_start)
            ).astype(np.float32)
            full_target = make_full_joint_target(
                commanded_action,
                robot.joint_names,
                default_by_robot_order=full_target,
                include_mimic=True,
            )
            robot.set_joint_position_target(torch.tensor(full_target, dtype=torch.float32, device=robot.device).view(1, -1))
            apply_gravity_compensation(robot, gravity_joint_ids)
            robot.write_data_to_sim()
            sim.step(render=True)
            update_scene(scene, sim_dt)
            actual_steps = step + 1

            if step % max(int(args_cli.video_every_n_steps), 1) == 0:
                frame = compose_video_frame(scene, schedule[phase_index], step, total_steps)
                if writer is None:
                    fps = 1.0 / (sim_dt * max(int(args_cli.video_every_n_steps), 1))
                    writer = VideoWriter(args_cli.output_video, fps, frame.shape)
                writer.write(frame)
            if step % 120 == 0:
                drawer_open = drawer_sign * float(scene["drawer"].data.joint_pos[0, drawer_joint_id].item())
                can_pos = scene["named_objects"]["can"].data.root_pos_w[0].detach().cpu().numpy()
                actual_action = extract_bimanual_state(robot.data.joint_pos[0].detach().cpu().numpy(), robot.joint_names)
                tracking = np.max(np.abs(commanded_action - actual_action))
                print(
                    f"[EVAL] step={step:04d}/{total_steps} phase={phase_index + 1:02d}/{len(schedule)} "
                    f"phase_frame={phase_frame:03d}/{schedule[phase_index]['frames']} "
                    f"drawer_open={drawer_open:.3f}m can=({can_pos[0]:.3f},{can_pos[1]:.3f},{can_pos[2]:.3f}) "
                    f"q_track_max={tracking:.3f}rad"
                )
    finally:
        if writer is not None:
            writer.close()
        server.close()
        if diagnostics:
            diagnostics[-1]["actual"] = extract_bimanual_state(
                robot.data.joint_pos[0].detach().cpu().numpy(), robot.joint_names
            )
        diagnostic_outputs = write_action_diagnostics(diagnostics)

    elapsed = time.monotonic() - start
    success_cfg = scripted_cfg.get("success", {})
    drawer_open = drawer_sign * float(scene["drawer"].data.joint_pos[0, drawer_joint_id].item())
    can_z = float(scene["named_objects"]["can"].data.root_pos_w[0, 2].item())
    drawer_limit = float(success_cfg.get("drawer_open_abs_max", 0.04))
    can_limits = success_cfg.get("can_world_z", {})
    can_min = float(can_limits.get("min_m", 0.8))
    can_max = float(can_limits.get("max_m", 1.15))
    drawer_ok = abs(drawer_open) < drawer_limit
    can_ok = can_min < can_z < can_max
    print(
        f"[EVAL] done complete={rollout_complete} success={drawer_ok and can_ok} "
        f"wall={elapsed:.1f}s sim={actual_steps * sim_dt:.1f}s "
        f"drawer={drawer_open:.3f}m (<{drawer_limit:.3f}) can_z={can_z:.3f}m ({can_min:.2f},{can_max:.2f})"
    )
    print(f"[EVAL] video={args_cli.output_video.resolve()}")
    if diagnostic_outputs is not None:
        print(f"[EVAL] diagnostics_csv={diagnostic_outputs[0].resolve()}")
        print(f"[EVAL] diagnostics_plot={diagnostic_outputs[1].resolve()}")


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
