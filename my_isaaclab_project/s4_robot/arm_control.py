"""Right-arm control helpers for S4 grasping debug."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import torch

from isaaclab.assets import Articulation, RigidObject
from isaaclab.utils.math import subtract_frame_transforms

from .control_mapping import ACTION_SLICES, BIMANUAL_ARM_HAND_JOINTS, bimanual_default_action
from .s4_robot_cfg import RIGHT_ARM_JOINTS, get_joint_limits


OPEN_RIGHT_HAND = np.array([0.5, 0.12, 0.05, 0.05, 0.05, 0.05], dtype=np.float32)
CLOSE_RIGHT_HAND = np.array([0.8, 0.48, 1.05, 1.05, 1.05, 1.05], dtype=np.float32)
DEFAULT_TCP_OFFSET_WRIST = np.array([0.0, 0.0, -0.10], dtype=np.float32)


@dataclass(frozen=True)
class ReachCommand:
    block_name: str
    offset: np.ndarray


def smooth_command(previous: np.ndarray, desired: np.ndarray, alpha: float, max_joint_step: float) -> np.ndarray:
    alpha = float(np.clip(alpha, 0.0, 1.0))
    max_step = max(float(max_joint_step), 1e-6)
    previous = np.nan_to_num(previous, nan=0.0, posinf=0.0, neginf=0.0)
    desired = np.nan_to_num(desired, nan=0.0, posinf=0.0, neginf=0.0)
    delta = np.clip(alpha * (desired - previous), -max_step, max_step)
    return previous + delta


def resolve_ordered_joints(robot: Articulation, names: list[str]) -> list[int]:
    ids, resolved = robot.find_joints([f"^{name}$" for name in names], preserve_order=True)
    if resolved != names:
        raise RuntimeError(f"Joint resolution mismatch. expected={names}, resolved={resolved}")
    return ids


def resolve_body(robot: Articulation, name: str) -> int:
    ids, _ = robot.find_bodies(f"^{name}$")
    if not ids:
        raise RuntimeError(f"Body not found: {name}")
    return ids[0]


def quat_rotate_wxyz(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    """Rotate 3-D vectors by quaternions in wxyz order."""
    q_w = quat[:, 0:1]
    q_xyz = quat[:, 1:4]
    uv = torch.cross(q_xyz, vec, dim=1)
    uuv = torch.cross(q_xyz, uv, dim=1)
    return vec + 2.0 * (q_w * uv + uuv)


class RightArmReachController:
    """Small-step Cartesian controller for moving the right wrist above a block."""

    def __init__(self, robot: Articulation, device: str):
        self.robot = robot
        self.device = device
        self.right_joint_ids = resolve_ordered_joints(robot, RIGHT_ARM_JOINTS)
        self.right_wrist_id = resolve_body(robot, "right_wrist_yaw_link")
        limits = get_joint_limits()
        self.lower_limits = torch.tensor(
            [limits[name]["lower"] for name in RIGHT_ARM_JOINTS],
            dtype=torch.float32,
            device=device,
        ).view(1, -1)
        self.upper_limits = torch.tensor(
            [limits[name]["upper"] for name in RIGHT_ARM_JOINTS],
            dtype=torch.float32,
            device=device,
        ).view(1, -1)
        self.neutral_q = torch.tensor(
            bimanual_default_action()[ACTION_SLICES.right_arm],
            dtype=torch.float32,
            device=device,
        ).view(1, -1)

    def rotate_wrist_vector_to_world(self, vec_wrist: torch.Tensor) -> torch.Tensor:
        wrist_pose_w = self.robot.data.body_pose_w[:, self.right_wrist_id]
        return quat_rotate_wxyz(wrist_pose_w[:, 3:7], vec_wrist)

    def clamp_right_arm_q(self, q: torch.Tensor) -> torch.Tensor:
        q = torch.nan_to_num(q, nan=0.0, posinf=0.0, neginf=0.0)
        return torch.maximum(torch.minimum(q, self.upper_limits), self.lower_limits)

    def update_action(
        self,
        action: np.ndarray,
        block: RigidObject,
        offset: Sequence[float],
        tcp_offset_wrist: Sequence[float] = DEFAULT_TCP_OFFSET_WRIST,
        hand_values: Sequence[float] = OPEN_RIGHT_HAND,
    ) -> tuple[np.ndarray, np.ndarray, float, np.ndarray, np.ndarray]:
        block_pos = block.data.root_pos_w[0].detach().cpu().numpy()
        target_tcp_pos = block_pos + np.asarray(offset, dtype=np.float32)

        root_pose_w = self.robot.data.root_pose_w
        wrist_pose_w = self.robot.data.body_pose_w[:, self.right_wrist_id]
        tcp_offset = torch.tensor(tcp_offset_wrist, dtype=torch.float32, device=self.device).view(1, 3)
        tcp_offset_w = self.rotate_wrist_vector_to_world(tcp_offset)
        target_wrist_pos_w = torch.tensor(target_tcp_pos, dtype=torch.float32, device=self.device).view(1, 3) - tcp_offset_w
        target_wrist_pos_b, _ = subtract_frame_transforms(
            root_pose_w[:, 0:3],
            root_pose_w[:, 3:7],
            target_wrist_pos_w,
            torch.tensor([[1.0, 0.0, 0.0, 0.0]], dtype=torch.float32, device=self.device),
        )

        wrist_pos_b, _ = subtract_frame_transforms(
            root_pose_w[:, 0:3],
            root_pose_w[:, 3:7],
            wrist_pose_w[:, 0:3],
            wrist_pose_w[:, 3:7],
        )
        pos_error_b = target_wrist_pos_b - wrist_pos_b
        error_norm = torch.linalg.norm(pos_error_b, dim=1, keepdim=True).clamp_min(1e-6)
        max_cart_step = 0.008
        step_error_b = pos_error_b * torch.clamp(max_cart_step / error_norm, max=1.0)

        jacobian_body_id = self.right_wrist_id - 1 if self.robot.is_fixed_base else self.right_wrist_id
        jacobian = self.robot.root_physx_view.get_jacobians()[:, jacobian_body_id, 0:3, self.right_joint_ids]
        damping = 0.08
        eye = torch.eye(3, dtype=torch.float32, device=self.device).unsqueeze(0)
        jj_t = jacobian @ jacobian.transpose(1, 2)
        j_pinv = jacobian.transpose(1, 2) @ torch.linalg.inv(jj_t + damping * damping * eye)
        dq = j_pinv @ step_error_b.unsqueeze(-1)

        current_q_t = self.clamp_right_arm_q(self.robot.data.joint_pos[:, self.right_joint_ids])
        identity_q = torch.eye(len(self.right_joint_ids), dtype=torch.float32, device=self.device).unsqueeze(0)
        nullspace = identity_q - j_pinv @ jacobian
        posture_step = 0.015 * (self.neutral_q - current_q_t)
        dq = dq + nullspace @ posture_step.unsqueeze(-1)
        dq = dq.squeeze(-1).clamp(-0.025, 0.025)

        target_q_t = self.clamp_right_arm_q(current_q_t + dq)

        current_q = current_q_t[0].detach().cpu().numpy()
        right_q_np = target_q_t[0].detach().cpu().numpy()
        desired = action.copy()
        desired[ACTION_SLICES.right_arm] = right_q_np
        desired[ACTION_SLICES.right_hand] = np.asarray(hand_values, dtype=np.float32)
        wrist_pos = wrist_pose_w[0, 0:3].detach().cpu().numpy()
        tcp_pos = wrist_pos + tcp_offset_w[0].detach().cpu().numpy()
        tcp_dist = float(np.linalg.norm(tcp_pos - target_tcp_pos))
        return desired, target_tcp_pos, tcp_dist, right_q_np, current_q


def write_default_control_file(path: Path, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    action = bimanual_default_action()
    payload = {
        "description": "Edit action or joints while joint-debug is running. `joints` overrides entries in `action`.",
        "action": [float(x) for x in action],
        "joints": {name: float(value) for name, value in zip(BIMANUAL_ARM_HAND_JOINTS, action, strict=True)},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_control_action(path: Path, fallback: np.ndarray) -> np.ndarray:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback

    if "action" in payload:
        action = np.asarray(payload["action"], dtype=np.float32)
        result = action if action.shape == fallback.shape else fallback.copy()
    else:
        result = fallback.copy()

    joints = payload.get("joints", {})
    if isinstance(joints, dict):
        name_to_idx = {name: i for i, name in enumerate(BIMANUAL_ARM_HAND_JOINTS)}
        for name, value in joints.items():
            if name in name_to_idx:
                result[name_to_idx[name]] = float(value)
    return result


class KeyboardJog:
    """Live joint jogging for continuous simulation debug."""

    def __init__(self, initial_action: np.ndarray, jog_step: float):
        self.action = initial_action.astype(np.float32, copy=True)
        self.jog_step = jog_step
        self.selected = 0
        self.pressed: set[str] = set()
        self._listener = None
        self._last_step = 0.0
        self._last_edge: set[str] = set()
        self._limits = get_joint_limits()

    def start(self) -> bool:
        try:
            from pynput import keyboard
        except ImportError:
            print("[WARN] pynput is not installed; keyboard joint jogging is disabled.")
            return False

        def key_name(key) -> str:
            try:
                return str(key.char).lower()
            except AttributeError:
                return getattr(key, "name", str(key)).lower()

        def on_press(key) -> None:
            self.pressed.add(key_name(key))

        def on_release(key) -> None:
            self.pressed.discard(key_name(key))

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()
        return True

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()

    def _pressed_once(self, key: str) -> bool:
        active = key in self.pressed
        was_active = key in self._last_edge
        if active:
            self._last_edge.add(key)
        else:
            self._last_edge.discard(key)
        return active and not was_active

    def _clamp_joint(self, joint_name: str, value: float) -> float:
        limits = self._limits.get(joint_name, {})
        return float(np.clip(value, limits.get("lower", -3.14), limits.get("upper", 3.14)))

    def update(self, action: np.ndarray) -> np.ndarray:
        self.action[:] = action

        if self._pressed_once("["):
            self.selected = (self.selected - 1) % len(BIMANUAL_ARM_HAND_JOINTS)
            print(f"[KEY] selected {self.selected}: {BIMANUAL_ARM_HAND_JOINTS[self.selected]}")
        if self._pressed_once("]"):
            self.selected = (self.selected + 1) % len(BIMANUAL_ARM_HAND_JOINTS)
            print(f"[KEY] selected {self.selected}: {BIMANUAL_ARM_HAND_JOINTS[self.selected]}")
        if self._pressed_once("r"):
            self.action[:] = bimanual_default_action()
            print("[KEY] reset 26-D action to default.")
        if self._pressed_once("p"):
            name = BIMANUAL_ARM_HAND_JOINTS[self.selected]
            print(f"[KEY] {self.selected}: {name}={self.action[self.selected]:.4f}")

        now = time.monotonic()
        if now - self._last_step >= 0.06:
            delta = 0.0
            if "u" in self.pressed:
                delta += float(self.jog_step)
            if "j" in self.pressed:
                delta -= float(self.jog_step)
            if delta != 0.0:
                name = BIMANUAL_ARM_HAND_JOINTS[self.selected]
                self.action[self.selected] = self._clamp_joint(name, float(self.action[self.selected] + delta))
                self._last_step = now
        return self.action.copy()
