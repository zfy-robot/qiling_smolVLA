#!/usr/bin/env python
"""Online SmolVLA rollout in the local S4 IsaacLab scene."""

from __future__ import annotations

import argparse
import base64
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PROJECT_DIR_FOR_DEFAULTS = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT_ROOT = PROJECT_DIR_FOR_DEFAULTS / "outputs/train/smolvla_s4_right_v1/checkpoints"

from isaaclab.app import AppLauncher


parser = argparse.ArgumentParser(description="Evaluate a SmolVLA checkpoint in the local S4 IsaacLab scene.")
parser.add_argument("--checkpoint", default=None, help="Checkpoint dir or pretrained_model dir. Defaults to latest local checkpoint.")
parser.add_argument("--steps", type=int, default=900)
parser.add_argument("--policy-every-n-steps", type=int, default=0, help="Policy query period in simulation steps. 0 means infer from the dataset/HDF5 used for training.")
parser.add_argument("--video-every-n-steps", type=int, default=2)
parser.add_argument("--output-video", type=Path, default=PROJECT_DIR_FOR_DEFAULTS / "outputs/eval/smolvla_rollout.avi")
parser.add_argument("--dataset-root", type=Path, default=PROJECT_DIR_FOR_DEFAULTS / "datasets/lerobot_data/s4_right_blue_cylinder_plate_v1")
parser.add_argument("--task-description", default=None)
parser.add_argument("--policy-python", default="/home/zfy/miniconda3/envs/smolvla/bin/python")
parser.add_argument("--policy-device", default="cuda", choices=["cuda", "cpu"])
parser.add_argument("--policy-startup-timeout", type=float, default=180.0)
parser.add_argument("--policy-request-timeout", type=float, default=60.0)
parser.add_argument("--policy-control-groups", nargs="+", default=["right_arm", "right_hand"], choices=["left_arm", "left_hand", "right_arm", "right_hand"])
parser.add_argument("--action-clip", default="dataset_minmax", choices=["none", "dataset_minmax", "dataset_q01_q99"])
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--camera-width", type=int, default=680)
parser.add_argument("--camera-height", type=int, default=480)
parser.add_argument("--robot-base-z", type=float, default=0.98)
parser.add_argument("--task-x", type=float, default=0.50)
parser.add_argument("--task-y", type=float, default=-0.05)
parser.add_argument("--block-y-offset", type=float, default=0.20)
parser.add_argument("--plate-x", type=float, default=0.50)
parser.add_argument("--camera-eye", type=float, nargs=3, default=[0.18, -0.62, 1.42])
parser.add_argument("--camera-target", type=float, nargs=3, default=[0.52, -0.12, 0.98])
parser.add_argument("--camera-rpy-deg", type=float, nargs=3, default=[-11.0, -26.0, -95.0])
parser.add_argument("--camera-convention", choices=["opengl", "ros", "world"], default="opengl")
parser.add_argument(
    "--camera-look-at",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Use --camera-eye -> --camera-target look-at for /World/DebugFrontCamera. Pass --no-camera-look-at to use --camera-rpy-deg.",
)
parser.add_argument("--joint-stiffness", type=float, default=600.0)
parser.add_argument("--joint-damping", type=float, default=80.0)
parser.add_argument("--joint-effort-limit", type=float, default=300.0)
parser.add_argument("--target-alpha", type=float, default=0.20)
parser.add_argument("--max-joint-step", type=float, default=0.035)
parser.add_argument("--hand-max-joint-step", type=float, default=0.010)
parser.add_argument("--reset-settle-steps", type=int, default=120)
parser.add_argument("--gravity-compensation", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--gravity-comp-scale", type=float, default=1.0)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import cv2
import numpy as np
import torch

from s4_robot.arm_control import smooth_command
from s4_robot.control_mapping import ACTION_SLICES, extract_bimanual_state, make_full_joint_target
from s4_robot.s4_robot_cfg import ALL_DRIVE_JOINTS
from s4_robot.simulation import (
    SceneBuildCfg,
    TASK_OBJECT_KEYS,
    TaskLayout,
    build_scene,
    create_simulation_context,
    format_layout,
    reset_camera,
    reset_scene,
)
from s4_pipeline.config import load_project_config


PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "s4_bimanual_dataset.json"
SERVER_PATH = Path(__file__).resolve().parent / "policy_server.py"
GROUP_SLICES = {
    "left_arm": ACTION_SLICES.left_arm,
    "left_hand": ACTION_SLICES.left_hand,
    "right_arm": ACTION_SLICES.right_arm,
    "right_hand": ACTION_SLICES.right_hand,
}
LEGACY_RIGHT_BLUE_TASK = "Use the left hand to put the red block into the tray and the right hand to put the blue block into the tray."
DEFAULT_STAGING_HDF5 = PROJECT_DIR / "datasets/staging/s4_right_blue_cylinder_plate_v1/s4_right_blue_cylinder_plate_scripted.hdf5"


def load_table_top_z() -> float:
    return float(load_project_config(CONFIG_PATH).scene.table_top_z)


def load_task_description() -> str:
    if args_cli.task_description:
        return str(args_cli.task_description)
    dataset_task = load_dataset_task_description()
    if dataset_task:
        return dataset_task
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return str(json.load(f)["dataset"]["task"])


def load_dataset_task_description() -> str | None:
    tasks_path = Path(args_cli.dataset_root) / "meta" / "tasks.parquet"
    if not tasks_path.exists():
        return None
    try:
        import pandas as pd

        tasks = pd.read_parquet(tasks_path)
        if "task" in tasks.columns and len(tasks):
            return str(tasks.iloc[0]["task"])
        if tasks.index.name == "task" and len(tasks.index):
            return str(tasks.index[0])
    except Exception as exc:
        legacy = infer_legacy_dataset()
        if legacy:
            print(f"[WARN] could not read dataset task parquet ({type(exc).__name__}: {exc}); using legacy 50-demo task text.")
            return LEGACY_RIGHT_BLUE_TASK
        print(f"[WARN] could not read dataset task parquet ({type(exc).__name__}: {exc}); falling back to config task.")
    return None


def infer_legacy_dataset() -> bool:
    info_path = Path(args_cli.dataset_root) / "meta" / "info.json"
    if not info_path.exists():
        return False
    try:
        with info_path.open("r", encoding="utf-8") as f:
            info = json.load(f)
        episodes = int(info.get("total_episodes", 0))
        frames = int(info.get("total_frames", 0))
        avg_frames = frames / max(episodes, 1)
        return episodes == 50 and avg_frames > 250
    except Exception:
        return False


def load_record_every_n_from_hdf5() -> int | None:
    if not DEFAULT_STAGING_HDF5.exists():
        return None
    try:
        import h5py

        with h5py.File(DEFAULT_STAGING_HDF5, "r") as f:
            env_args = json.loads(f["data"].attrs.get("env_args", "{}"))
        value = env_args.get("record_every_n")
        if value is not None:
            return max(int(value), 1)
    except Exception as exc:
        print(f"[WARN] could not read HDF5 record_every_n ({type(exc).__name__}: {exc})")
    return None


def resolve_policy_every_n_steps() -> int:
    explicit = int(args_cli.policy_every_n_steps)
    if explicit > 0:
        return explicit
    from_hdf5 = load_record_every_n_from_hdf5()
    if from_hdf5 is not None:
        return from_hdf5
    if infer_legacy_dataset():
        print("[EVAL] inferred legacy 50-demo dataset; using policy_every_n_steps=2 to match old record_every_n=2.")
        return 2
    return 6


def load_action_bounds() -> tuple[np.ndarray | None, np.ndarray | None]:
    if args_cli.action_clip == "none":
        return None, None
    stats_path = Path(args_cli.dataset_root) / "meta" / "stats.json"
    if not stats_path.exists():
        print(f"[WARN] action stats not found, disabling action clipping: {stats_path}")
        return None, None
    with stats_path.open("r", encoding="utf-8") as f:
        stats = json.load(f)["action"]
    if args_cli.action_clip == "dataset_q01_q99":
        low_key, high_key = "q01", "q99"
    else:
        low_key, high_key = "min", "max"
    low = np.asarray(stats[low_key], dtype=np.float32)
    high = np.asarray(stats[high_key], dtype=np.float32)
    if low.ndim != 1 or high.ndim != 1 or low.shape != high.shape or low.shape[0] not in {13, 26}:
        print(f"[WARN] invalid action stats shape, disabling action clipping: low={low.shape} high={high.shape}")
        return None, None
    return low, high


def load_dataset_feature_dims() -> tuple[int, int]:
    info_path = Path(args_cli.dataset_root) / "meta" / "info.json"
    if not info_path.exists():
        return 48, 26
    try:
        with info_path.open("r", encoding="utf-8") as f:
            features = json.load(f).get("features", {})
        state_dim = int(features.get("observation.state", {}).get("shape", [48])[0])
        action_dim = int(features.get("action", {}).get("shape", [26])[0])
        return state_dim, action_dim
    except Exception as exc:
        print(f"[WARN] could not read dataset feature dims ({type(exc).__name__}: {exc}); using 48/26.")
        return 48, 26


def make_scene_cfg() -> SceneBuildCfg:
    project_cfg = load_project_config(CONFIG_PATH)
    return SceneBuildCfg(
        table_top_z=load_table_top_z(),
        joint_stiffness=float(args_cli.joint_stiffness),
        joint_damping=float(args_cli.joint_damping),
        joint_effort_limit=float(args_cli.joint_effort_limit),
        scene_usd=project_cfg.scene.scene_usd,
        table_usd=project_cfg.scene.table_usd,
        robot_base_z=float(args_cli.robot_base_z),
        layout=TaskLayout(
            table_center_x=float(args_cli.task_x),
            table_center_y=float(args_cli.task_y),
            block_x=float(args_cli.task_x),
            block_y_offset=float(args_cli.block_y_offset),
            plate_x=float(args_cli.plate_x),
        ),
        camera_eye=tuple(float(x) for x in args_cli.camera_eye),
        camera_target=tuple(float(x) for x in args_cli.camera_target),
        camera_rpy_deg=None if args_cli.camera_look_at else tuple(float(x) for x in args_cli.camera_rpy_deg),
        camera_convention=str(args_cli.camera_convention),
        camera_width=max(int(args_cli.camera_width), 1),
        camera_height=max(int(args_cli.camera_height), 1),
    )


def camera_rgb_uint8(camera) -> np.ndarray:
    rgb = camera.data.output["rgb"][0].detach().cpu().numpy()
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0.0, 1.0)
        rgb = (rgb * 255.0).astype(np.uint8)
    if rgb.shape[-1] > 3:
        rgb = rgb[..., :3]
    return rgb


def resolve_existing_joint_ids(robot, joint_names: list[str]) -> list[int]:
    return [robot.joint_names.index(name) for name in joint_names if name in robot.joint_names]


def apply_gravity_compensation(robot, joint_ids: list[int]) -> tuple[float, float]:
    if not joint_ids or not args_cli.gravity_compensation:
        if joint_ids:
            robot.set_joint_effort_target(torch.zeros(1, len(joint_ids), dtype=torch.float32, device=robot.device), joint_ids=joint_ids)
        return 0.0, 0.0
    gravity = robot.root_physx_view.get_gravity_compensation_forces()
    if gravity.shape[1] <= max(joint_ids):
        return 0.0, 0.0
    efforts = gravity[:, joint_ids] * float(args_cli.gravity_comp_scale)
    robot.set_joint_effort_target(efforts, joint_ids=joint_ids)
    abs_efforts = torch.abs(efforts)
    return float(torch.max(abs_efforts)), float(torch.mean(abs_efforts))


def settle_scene(scene: dict[str, object], camera, full_target: np.ndarray, sim, steps: int) -> None:
    robot = scene["robot"]
    target_tensor = torch.tensor(full_target, dtype=torch.float32, device=robot.device).view(1, -1)
    for _ in range(max(int(steps), 0)):
        robot.set_joint_position_target(target_tensor)
        robot.write_data_to_sim()
        sim.step(render=True)
        robot.update(dt=sim.get_physics_dt())
        for key in TASK_OBJECT_KEYS:
            scene[key].update(dt=sim.get_physics_dt())
        camera.update(dt=sim.get_physics_dt())


def make_policy_server_env() -> dict[str, str]:
    env = os.environ.copy()
    policy_python = Path(args_cli.policy_python).expanduser().resolve()
    policy_prefix = policy_python.parent.parent
    hf_home = PROJECT_DIR / ".cache" / "huggingface"

    env["CONDA_PREFIX"] = str(policy_prefix)
    env["PATH"] = f"{policy_prefix / 'bin'}:/usr/bin:/bin"
    env.pop("PYTHONPATH", None)
    env["LD_LIBRARY_PATH"] = str(policy_prefix / "lib")
    env["HF_HOME"] = str(hf_home)
    env["HF_HUB_CACHE"] = str(hf_home / "hub")
    env["HF_DATASETS_CACHE"] = str(hf_home / "datasets")
    env["TRANSFORMERS_CACHE"] = str(hf_home / "transformers")
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("HUGGINGFACE_HUB_OFFLINE", "1")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")
    return env


def list_available_checkpoints(root: Path = DEFAULT_CHECKPOINT_ROOT) -> list[Path]:
    if not root.exists():
        return []
    candidates = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]
    candidates.sort(key=lambda p: int(p.name))
    return candidates


def latest_checkpoint() -> Path:
    candidates = list_available_checkpoints()
    if not candidates:
        raise FileNotFoundError(f"No numeric checkpoints found under: {DEFAULT_CHECKPOINT_ROOT}")
    return candidates[-1] / "pretrained_model"


def resolve_checkpoint(path: str | None) -> Path:
    if path is None:
        ckpt = latest_checkpoint()
    else:
        ckpt = Path(path).expanduser()
        if (ckpt / "checkpoints").exists():
            nested = [p for p in (ckpt / "checkpoints").iterdir() if p.is_dir() and p.name.isdigit()]
            nested.sort(key=lambda p: int(p.name))
            if nested:
                ckpt = nested[-1] / "pretrained_model"
        elif (ckpt / "pretrained_model").exists():
            ckpt = ckpt / "pretrained_model"
    if not (ckpt / "config.json").exists():
        available = ", ".join(p.name for p in list_available_checkpoints()) or "<none>"
        raise FileNotFoundError(
            f"SmolVLA pretrained_model config.json not found: {ckpt}\n"
            f"Available checkpoints under {DEFAULT_CHECKPOINT_ROOT}: {available}"
        )
    return ckpt


class PolicyServer:
    def __init__(self, checkpoint: Path):
        cmd = [
            args_cli.policy_python,
            str(SERVER_PATH),
            "--checkpoint",
            str(checkpoint),
            "--device",
            args_cli.policy_device,
            "--seed",
            str(args_cli.seed),
        ]
        print("[EVAL] starting policy server:")
        print("[EVAL]   " + " ".join(cmd))
        policy_env = make_policy_server_env()
        print(f"[EVAL] policy env CONDA_PREFIX={policy_env.get('CONDA_PREFIX', '')}")
        print(f"[EVAL] policy env PYTHONPATH={policy_env.get('PYTHONPATH', '<unset>')}")
        print(
            f"[EVAL] waiting for policy server ready "
            f"(timeout={float(args_cli.policy_startup_timeout):.0f}s, device={args_cli.policy_device})"
        )
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
            env=policy_env,
        )
        try:
            ready = self._read(timeout=float(args_cli.policy_startup_timeout), context="startup")
            if ready.get("status") != "ready":
                raise RuntimeError(f"Policy server did not become ready: {ready}")
            print(f"[EVAL] policy server ready: {ready}")
        except Exception:
            self.close()
            raise

    def _read(self, timeout: float, context: str) -> dict:
        assert self.proc.stdout is not None
        deadline = time.monotonic() + max(float(timeout), 0.1)
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Policy server exited during {context} with code {self.proc.returncode}.")
            ready, _, _ = select.select([self.proc.stdout], [], [], min(1.0, max(deadline - time.monotonic(), 0.0)))
            if not ready:
                continue
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError(f"Policy server closed stdout during {context}.")
            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Policy server wrote non-JSON stdout during {context}: {line.strip()}") from exc
        raise TimeoutError(
            f"Timed out waiting for policy server during {context} after {timeout:.0f}s. "
            "For a first smoke test, try adding '--policy-device cpu --steps 20'. "
            "If CUDA is used, the SmolVLA server may be competing with IsaacSim for GPU memory."
        )

    def reset(self) -> None:
        self.request({"command": "reset"})

    def request(self, payload: dict) -> dict:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        response = self._read(timeout=float(args_cli.policy_request_timeout), context="request")
        if "error" in response:
            raise RuntimeError(response["error"])
        return response

    def action(self, state: np.ndarray, image: np.ndarray, task: str) -> np.ndarray:
        response = self.request(
            {
                "state": state.astype(float).tolist(),
                "image_shape": list(image.shape),
                "image_b64": base64.b64encode(image.tobytes()).decode("ascii"),
                "task": task,
            }
        )
        action = np.asarray(response["action"], dtype=np.float32)
        if action.shape not in {(13,), (26,)}:
            raise ValueError(f"Policy returned action shape {action.shape}, expected (13,) or (26,)")
        return action

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class VideoWriter:
    def __init__(self, path: Path, fps: int, frame_shape: tuple[int, int, int]):
        path.parent.mkdir(parents=True, exist_ok=True)
        h, w = frame_shape[:2]
        suffix = path.suffix.lower()
        fourcc_name = "MJPG" if suffix == ".avi" else "mp4v"
        self.writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc_name), float(fps), (w, h))
        if not self.writer.isOpened():
            raise RuntimeError(f"Failed to open video writer: {path}")
        self.path = path

    def write(self, rgb: np.ndarray) -> None:
        self.writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    def close(self) -> None:
        self.writer.release()


def overlay_status(
    rgb: np.ndarray,
    step: int,
    blue_pos: np.ndarray,
    plate_pos: np.ndarray,
    action: np.ndarray,
    actual_state: np.ndarray,
) -> np.ndarray:
    frame = rgb.copy()
    dist_xy = float(np.linalg.norm(blue_pos[:2] - plate_pos[:2]))
    lines = [
        f"step={step}",
        f"blue=({blue_pos[0]:.2f},{blue_pos[1]:.2f},{blue_pos[2]:.2f}) plate=({plate_pos[0]:.2f},{plate_pos[1]:.2f},{plate_pos[2]:.2f})",
        f"blue_plate_xy_dist={dist_xy:.3f}m",
        "right_arm=" + ",".join(f"{x:+.2f}" for x in action[ACTION_SLICES.right_arm]),
        "cmd_right_hand=" + ",".join(f"{x:+.2f}" for x in action[ACTION_SLICES.right_hand]),
        "act_right_hand=" + ",".join(f"{x:+.2f}" for x in actual_state[ACTION_SLICES.right_hand]),
    ]
    y = 18
    for line in lines:
        cv2.putText(frame, line, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
        y += 16
    return frame


def apply_policy_action_filter(
    raw_action: np.ndarray,
    current_action: np.ndarray,
    low: np.ndarray | None,
    high: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
    filtered = current_action.copy()
    clipped = raw_action.copy()
    if low is not None and high is not None:
        clipped = np.clip(clipped, low, high)
    if clipped.shape == (13,):
        filtered[ACTION_SLICES.right_arm] = clipped[:7]
        filtered[ACTION_SLICES.right_hand] = clipped[7:13]
        return filtered.astype(np.float32), clipped.astype(np.float32)
    if clipped.shape != (26,):
        raise ValueError(f"Policy action must have shape (13,) or (26,), got {clipped.shape}")
    for group in args_cli.policy_control_groups:
        sl = GROUP_SLICES[group]
        filtered[sl] = clipped[sl]
    return filtered.astype(np.float32), clipped.astype(np.float32)


def format_group_values(prefix: str, action: np.ndarray) -> str:
    if action.shape == (13,):
        return (
            f"{prefix} "
            f"RA=[" + ",".join(f"{x:+.3f}" for x in action[:7]) + "] "
            f"RH=[" + ",".join(f"{x:+.3f}" for x in action[7:13]) + "]"
        )
    return (
        f"{prefix} "
        f"RA=[" + ",".join(f"{x:+.3f}" for x in action[ACTION_SLICES.right_arm]) + "] "
        f"RH=[" + ",".join(f"{x:+.3f}" for x in action[ACTION_SLICES.right_hand]) + "]"
    )


def format_right_hand_tracking(commanded_action: np.ndarray, actual_state: np.ndarray) -> str:
    cmd = commanded_action[ACTION_SLICES.right_hand]
    actual = actual_state[ACTION_SLICES.right_hand]
    err = cmd - actual
    return (
        "RH_tracking "
        f"cmd=[" + ",".join(f"{x:+.3f}" for x in cmd) + "] "
        f"actual=[" + ",".join(f"{x:+.3f}" for x in actual) + "] "
        f"max_err={np.max(np.abs(err)):.4f}"
    )


def main() -> None:
    cfg = make_scene_cfg()
    print(format_layout(cfg))
    task_description = load_task_description()
    action_low, action_high = load_action_bounds()
    dataset_state_dim, dataset_action_dim = load_dataset_feature_dims()
    policy_every_n_steps = resolve_policy_every_n_steps()
    checkpoint = resolve_checkpoint(args_cli.checkpoint)
    print(f"[EVAL] task={task_description!r}")
    print(f"[EVAL] checkpoint={checkpoint}")
    print(
        f"[EVAL] policy_control_groups={','.join(args_cli.policy_control_groups)} "
        f"action_clip={args_cli.action_clip} policy_every_n_steps={policy_every_n_steps} "
        f"dataset_state_dim={dataset_state_dim} dataset_action_dim={dataset_action_dim}"
    )
    sim = create_simulation_context(args_cli.device)
    scene = build_scene(cfg)
    sim.reset()
    reset_camera(scene["camera"], sim, cfg)
    default_target = reset_scene(scene, cfg, sim)
    settle_scene(scene, scene["camera"], default_target, sim, args_cli.reset_settle_steps)

    robot = scene["robot"]
    camera = scene["camera"]
    sim_dt = sim.get_physics_dt()
    gravity_joint_ids = resolve_existing_joint_ids(robot, list(ALL_DRIVE_JOINTS))
    commanded_action = extract_bimanual_state(robot.data.joint_pos[0].detach().cpu().numpy(), robot.joint_names)
    desired_action = commanded_action.copy()
    full_target = default_target.copy()
    video = None
    server = PolicyServer(checkpoint)
    server.reset()
    last_action = commanded_action.copy()
    last_gravity = (0.0, 0.0)
    start = time.monotonic()

    try:
        for step in range(max(int(args_cli.steps), 1)):
            if step % policy_every_n_steps == 0:
                if dataset_state_dim == 13:
                    state = extract_bimanual_state(
                        robot.data.joint_pos[0].detach().cpu().numpy(),
                        robot.joint_names,
                    )[ACTION_SLICES.right_arm.start : ACTION_SLICES.right_hand.stop].astype(np.float32)
                else:
                    state = robot.data.joint_pos[0].detach().cpu().numpy().astype(np.float32)
                image = camera_rgb_uint8(camera)
                raw_policy_action = server.action(state, image, task_description)
                desired_action, clipped_policy_action = apply_policy_action_filter(
                    raw_policy_action,
                    commanded_action,
                    action_low,
                    action_high,
                )
                if step == 0 or step % 120 == 0:
                    print("[EVAL] " + format_group_values("raw_policy", raw_policy_action))
                    print("[EVAL] " + format_group_values("clipped_policy", clipped_policy_action))
                    print("[EVAL] " + format_group_values("desired", desired_action))
            next_action = smooth_command(
                commanded_action,
                desired_action,
                alpha=float(args_cli.target_alpha),
                max_joint_step=float(args_cli.max_joint_step),
            )
            hand_delta = np.clip(
                next_action[ACTION_SLICES.right_hand] - commanded_action[ACTION_SLICES.right_hand],
                -float(args_cli.hand_max_joint_step),
                float(args_cli.hand_max_joint_step),
            )
            next_action[ACTION_SLICES.right_hand] = commanded_action[ACTION_SLICES.right_hand] + hand_delta
            commanded_action = next_action.astype(np.float32)
            last_action = commanded_action.copy()
            full_target = make_full_joint_target(
                commanded_action,
                robot.joint_names,
                default_by_robot_order=full_target,
                include_mimic=True,
            )
            robot.set_joint_position_target(torch.tensor(full_target, dtype=torch.float32, device=robot.device).view(1, -1))
            last_gravity = apply_gravity_compensation(robot, gravity_joint_ids)
            robot.write_data_to_sim()
            sim.step(render=True)
            robot.update(dt=sim_dt)
            for key in TASK_OBJECT_KEYS:
                scene[key].update(dt=sim_dt)
            camera.update(dt=sim_dt)

            if step % max(int(args_cli.video_every_n_steps), 1) == 0:
                rgb = camera_rgb_uint8(camera)
                blue = scene["blue"].data.root_pos_w[0].detach().cpu().numpy()
                plate = scene["plate"].data.root_pos_w[0].detach().cpu().numpy()
                actual_state = extract_bimanual_state(robot.data.joint_pos[0].detach().cpu().numpy(), robot.joint_names)
                frame = overlay_status(rgb, step, blue, plate, commanded_action, actual_state)
                if video is None:
                    video = VideoWriter(args_cli.output_video, fps=max(int(1.0 / sim_dt / max(int(args_cli.video_every_n_steps), 1)), 1), frame_shape=frame.shape)
                video.write(frame)
            if step % 120 == 0:
                blue = scene["blue"].data.root_pos_w[0].detach().cpu().numpy()
                plate = scene["plate"].data.root_pos_w[0].detach().cpu().numpy()
                actual_state = extract_bimanual_state(robot.data.joint_pos[0].detach().cpu().numpy(), robot.joint_names)
                print(
                    f"[EVAL] step={step} blue=({blue[0]:.3f},{blue[1]:.3f},{blue[2]:.3f}) "
                    f"plate=({plate[0]:.3f},{plate[1]:.3f},{plate[2]:.3f}) "
                    f"xy_dist={np.linalg.norm(blue[:2] - plate[:2]):.3f} "
                    f"gravity=max:{last_gravity[0]:.2f}/mean:{last_gravity[1]:.2f}"
                )
                print("[EVAL] " + format_right_hand_tracking(commanded_action, actual_state))
    finally:
        if video is not None:
            video.close()
        server.close()
    elapsed = time.monotonic() - start
    blue = scene["blue"].data.root_pos_w[0].detach().cpu().numpy()
    plate = scene["plate"].data.root_pos_w[0].detach().cpu().numpy()
    print(
        f"[EVAL] done steps={args_cli.steps} wall_seconds={elapsed:.1f} "
        f"final_blue=({blue[0]:.3f},{blue[1]:.3f},{blue[2]:.3f}) "
        f"plate=({plate[0]:.3f},{plate[1]:.3f},{plate[2]:.3f}) "
        f"xy_dist={np.linalg.norm(blue[:2] - plate[:2]):.3f}"
    )
    print(f"[EVAL] video={args_cli.output_video}")


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
