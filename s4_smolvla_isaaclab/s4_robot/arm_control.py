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
from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
from isaaclab.utils.math import (
    combine_frame_transforms,
    compute_pose_error,
    matrix_from_quat,
    quat_inv,
    skew_symmetric_matrix,
    subtract_frame_transforms,
)

from .control_mapping import ACTION_SLICES, BIMANUAL_ARM_HAND_JOINTS, bimanual_default_action
from .s4_robot_cfg import RIGHT_ARM_JOINTS, get_joint_limits


OPEN_RIGHT_HAND = np.array([0.9, 0.0, 0.05, 0.05, 0.05, 0.05], dtype=np.float32)
CLOSE_RIGHT_HAND = np.array([1.0, 0.42, 0.85, 0.85, 0.85, 0.85], dtype=np.float32)
DEFAULT_TCP_OFFSET_WRIST = np.array([0.0, 0.0, -0.10], dtype=np.float32)
DEFAULT_MAX_CART_STEP = 0.004
DEFAULT_MAX_JOINT_DELTA = 0.010
DEFAULT_DLS_DAMPING = 0.16
DEFAULT_POSTURE_GAIN = 0.30
DEFAULT_MAX_REACH_ERROR = 0.85
DEFAULT_MIN_TCP_BELOW_BLOCK = 0.04
DEFAULT_JACOBIAN_SIGN = 1.0


@dataclass(frozen=True)
class ReachCommand:
    block_name: str
    offset: np.ndarray


@dataclass(frozen=True)
class ReachDebug:
    block_pos: np.ndarray
    target_tcp_pos: np.ndarray
    current_tcp_pos: np.ndarray
    target_tcp_quat: np.ndarray
    current_tcp_quat: np.ndarray
    tcp_error: np.ndarray
    rot_error_axis_angle: np.ndarray
    tcp_dist: float
    target_wrist_pos: np.ndarray
    offset_world: np.ndarray
    offset_frame: str
    step_error_world: np.ndarray
    predicted_tcp_delta: np.ndarray
    joint_delta: np.ndarray
    jacobian_body_row: int
    jacobian_sign: float
    direction_sign: float
    actual_delta_world: np.ndarray
    actual_progress: float
    held_for_safety: bool
    safety_reason: str = ""


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

    def __init__(
        self,
        robot: Articulation,
        device: str,
        max_cart_step: float = DEFAULT_MAX_CART_STEP,
        max_joint_delta: float = DEFAULT_MAX_JOINT_DELTA,
        damping: float = DEFAULT_DLS_DAMPING,
        posture_gain: float = DEFAULT_POSTURE_GAIN,
        max_reach_error: float = DEFAULT_MAX_REACH_ERROR,
        jacobian_body_shift: int | None = None,
        jacobian_sign: float = DEFAULT_JACOBIAN_SIGN,
        adaptive_direction_sign: bool = False,
        min_tcp_below_block: float = DEFAULT_MIN_TCP_BELOW_BLOCK,
    ):
        self.robot = robot
        self.device = device
        self.right_joint_ids = resolve_ordered_joints(robot, RIGHT_ARM_JOINTS)
        self.right_wrist_id = resolve_body(robot, "right_wrist_yaw_link")
        self.max_cart_step = float(max_cart_step)
        self.max_joint_delta = float(max_joint_delta)
        self.damping = float(damping)
        self.posture_gain = float(posture_gain)
        self.max_reach_error = float(max_reach_error)
        self.jacobian_body_shift = jacobian_body_shift
        self.jacobian_sign = 1.0 if float(jacobian_sign) >= 0.0 else -1.0
        self.adaptive_direction_sign = bool(adaptive_direction_sign)
        self.min_tcp_below_block = float(min_tcp_below_block)
        self.direction_sign = 1.0
        self._last_tcp_pos: np.ndarray | None = None
        self._last_tcp_error: np.ndarray | None = None
        self._last_predicted_tcp_delta: np.ndarray | None = None
        self._bad_progress_count = 0
        ik_cfg = DifferentialIKControllerCfg(
            command_type="position",
            use_relative_mode=False,
            ik_method="dls",
            ik_params={"lambda_val": self.damping},
        )
        self.ik_controller = DifferentialIKController(ik_cfg, num_envs=1, device=device)
        pose_ik_cfg = DifferentialIKControllerCfg(
            command_type="pose",
            use_relative_mode=False,
            ik_method="dls",
            ik_params={"lambda_val": self.damping},
        )
        self.pose_ik_controller = DifferentialIKController(pose_ik_cfg, num_envs=1, device=device)
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

    def reset_diagnostics(self) -> None:
        self.direction_sign = 1.0
        self._last_tcp_pos = None
        self._last_tcp_error = None
        self._last_predicted_tcp_delta = None
        self._bad_progress_count = 0
        self.ik_controller.reset()
        self.pose_ik_controller.reset()

    def default_jacobian_body_row(self) -> int:
        default_shift = -1 if self.robot.is_fixed_base else 0
        body_shift = default_shift if self.jacobian_body_shift is None else int(self.jacobian_body_shift)
        return self.right_wrist_id + body_shift

    def resolution_summary(self) -> str:
        return (
            f"right_wrist_body={self.right_wrist_id}:{self.robot.body_names[self.right_wrist_id]} "
            f"jac_row={self.default_jacobian_body_row()} "
            f"right_joint_ids={self.right_joint_ids} "
            f"right_joint_names={RIGHT_ARM_JOINTS}"
        )

    def _make_debug(
        self,
        block_pos: np.ndarray,
        target_tcp_pos: np.ndarray,
        current_tcp_pos: np.ndarray,
        target_tcp_quat: np.ndarray,
        current_tcp_quat: np.ndarray,
        tcp_error: np.ndarray,
        rot_error_axis_angle: np.ndarray | None,
        tcp_dist: float,
        target_wrist_pos: np.ndarray,
        offset_world: np.ndarray,
        offset_frame: str,
        step_error_world: np.ndarray | None = None,
        predicted_tcp_delta: np.ndarray | None = None,
        joint_delta: np.ndarray | None = None,
        jacobian_body_row: int = -1,
        actual_delta_world: np.ndarray | None = None,
        actual_progress: float = 0.0,
        held_for_safety: bool = False,
        safety_reason: str = "",
    ) -> ReachDebug:
        return ReachDebug(
            block_pos=block_pos,
            target_tcp_pos=target_tcp_pos,
            current_tcp_pos=current_tcp_pos,
            target_tcp_quat=target_tcp_quat,
            current_tcp_quat=current_tcp_quat,
            tcp_error=tcp_error,
            rot_error_axis_angle=np.zeros(3, dtype=np.float32) if rot_error_axis_angle is None else rot_error_axis_angle,
            tcp_dist=tcp_dist,
            target_wrist_pos=target_wrist_pos,
            offset_world=offset_world,
            offset_frame=offset_frame,
            step_error_world=np.zeros(3, dtype=np.float32) if step_error_world is None else step_error_world,
            predicted_tcp_delta=np.zeros(3, dtype=np.float32) if predicted_tcp_delta is None else predicted_tcp_delta,
            joint_delta=np.zeros(len(RIGHT_ARM_JOINTS), dtype=np.float32) if joint_delta is None else joint_delta,
            jacobian_body_row=jacobian_body_row,
            jacobian_sign=self.jacobian_sign,
            direction_sign=self.direction_sign,
            actual_delta_world=np.zeros(3, dtype=np.float32) if actual_delta_world is None else actual_delta_world,
            actual_progress=float(actual_progress),
            held_for_safety=held_for_safety,
            safety_reason=safety_reason,
        )

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
        offset_frame: str = "world",
        target_block_pos_w: Sequence[float] | None = None,
        target_tcp_quat_w: Sequence[float] | None = None,
    ) -> tuple[np.ndarray, ReachDebug, np.ndarray, np.ndarray]:
        if target_block_pos_w is None:
            block_pos = block.data.root_pos_w[0].detach().cpu().numpy()
        else:
            block_pos = np.asarray(target_block_pos_w, dtype=np.float32)
            if block_pos.shape != (3,):
                raise ValueError(f"target_block_pos_w must have shape (3,), got {block_pos.shape}")
        wrist_pose_w = self.robot.data.body_pose_w[:, self.right_wrist_id]
        offset_np = np.asarray(offset, dtype=np.float32)
        offset_t = torch.tensor(offset_np, dtype=torch.float32, device=self.device).view(1, 3)
        if offset_frame == "wrist":
            offset_world_t = self.rotate_wrist_vector_to_world(offset_t)
            offset_world = offset_world_t[0].detach().cpu().numpy()
        elif offset_frame == "world":
            offset_world = offset_np
        else:
            raise ValueError(f"offset_frame must be 'world' or 'wrist', got {offset_frame!r}")
        target_tcp_pos = block_pos + offset_world

        tcp_offset = torch.tensor(tcp_offset_wrist, dtype=torch.float32, device=self.device).view(1, 3)
        tcp_offset_w = self.rotate_wrist_vector_to_world(tcp_offset)
        target_tcp_pos_w_t = torch.tensor(target_tcp_pos, dtype=torch.float32, device=self.device).view(1, 3)
        target_wrist_pos_w = target_tcp_pos_w_t - tcp_offset_w
        wrist_pos_w = wrist_pose_w[:, 0:3]
        wrist_quat_w = wrist_pose_w[:, 3:7]
        tcp_pos_w = wrist_pos_w + tcp_offset_w
        tcp_quat_w = wrist_quat_w
        current_tcp_pos = tcp_pos_w[0].detach().cpu().numpy()
        current_tcp_quat = tcp_quat_w[0].detach().cpu().numpy()
        if target_tcp_quat_w is None:
            target_tcp_quat_w_t = tcp_quat_w
            target_tcp_quat = current_tcp_quat.copy()
            use_pose_ik = False
        else:
            target_tcp_quat = np.asarray(target_tcp_quat_w, dtype=np.float32)
            if target_tcp_quat.shape != (4,):
                raise ValueError(f"target_tcp_quat_w must have shape (4,), got {target_tcp_quat.shape}")
            target_tcp_quat_w_t = torch.tensor(target_tcp_quat, dtype=torch.float32, device=self.device).view(1, 4)
            target_tcp_quat_w_t = target_tcp_quat_w_t / torch.linalg.norm(
                target_tcp_quat_w_t, dim=1, keepdim=True
            ).clamp_min(1e-6)
            target_tcp_quat = target_tcp_quat_w_t[0].detach().cpu().numpy()
            use_pose_ik = True
        tcp_error_w = target_tcp_pos - current_tcp_pos
        rot_error_axis_angle = np.zeros(3, dtype=np.float32)
        tcp_dist = float(np.linalg.norm(tcp_error_w))
        actual_progress = 0.0
        actual_delta = np.zeros(3, dtype=np.float32)
        if self._last_tcp_pos is not None and self._last_tcp_error is not None:
            actual_delta = current_tcp_pos - self._last_tcp_pos
            previous_error_norm = max(float(np.linalg.norm(self._last_tcp_error)), 1e-6)
            actual_progress = float(np.dot(actual_delta, self._last_tcp_error) / previous_error_norm)
            if self.adaptive_direction_sign and actual_progress < -1e-5:
                self._bad_progress_count += 1
            elif actual_progress > 1e-5:
                self._bad_progress_count = 0
            if self.adaptive_direction_sign and self._bad_progress_count >= 8:
                self.direction_sign *= -1.0
                self._bad_progress_count = 0
        current_q_t = self.clamp_right_arm_q(self.robot.data.joint_pos[:, self.right_joint_ids])
        current_q = current_q_t[0].detach().cpu().numpy()

        if not np.isfinite(tcp_dist) or tcp_dist > self.max_reach_error:
            debug = self._make_debug(
                block_pos=block_pos,
                target_tcp_pos=target_tcp_pos,
                current_tcp_pos=current_tcp_pos,
                target_tcp_quat=target_tcp_quat,
                current_tcp_quat=current_tcp_quat,
                tcp_error=tcp_error_w,
                rot_error_axis_angle=rot_error_axis_angle,
                tcp_dist=tcp_dist,
                target_wrist_pos=target_wrist_pos_w[0].detach().cpu().numpy(),
                offset_world=offset_world,
                offset_frame=offset_frame,
                actual_delta_world=actual_delta,
                held_for_safety=True,
                safety_reason=f"tcp_dist {tcp_dist:.3f} exceeds max_reach_error {self.max_reach_error:.3f}",
            )
            desired = action.copy()
            desired[ACTION_SLICES.right_hand] = np.asarray(hand_values, dtype=np.float32)
            return desired, debug, current_q, current_q
        if current_tcp_pos[2] < block_pos[2] - self.min_tcp_below_block:
            debug = self._make_debug(
                block_pos=block_pos,
                target_tcp_pos=target_tcp_pos,
                current_tcp_pos=current_tcp_pos,
                target_tcp_quat=target_tcp_quat,
                current_tcp_quat=current_tcp_quat,
                tcp_error=tcp_error_w,
                rot_error_axis_angle=rot_error_axis_angle,
                tcp_dist=tcp_dist,
                target_wrist_pos=target_wrist_pos_w[0].detach().cpu().numpy(),
                offset_world=offset_world,
                offset_frame=offset_frame,
                actual_delta_world=actual_delta,
                actual_progress=actual_progress,
                held_for_safety=True,
                safety_reason=(
                    f"tcp_z {current_tcp_pos[2]:.3f} below block_z {block_pos[2]:.3f} "
                    f"by more than {self.min_tcp_below_block:.3f}m"
                ),
            )
            desired = action.copy()
            desired[ACTION_SLICES.right_arm] = current_q
            desired[ACTION_SLICES.right_hand] = np.asarray(hand_values, dtype=np.float32)
            self._last_tcp_pos = current_tcp_pos.copy()
            self._last_tcp_error = tcp_error_w.copy()
            return desired, debug, current_q, current_q

        jacobians = self.robot.root_physx_view.get_jacobians()
        default_shift = -1 if self.robot.is_fixed_base else 0
        body_shift = default_shift if self.jacobian_body_shift is None else int(self.jacobian_body_shift)
        jacobian_body_id = int(np.clip(self.right_wrist_id + body_shift, 0, jacobians.shape[1] - 1))
        body_jacobian = jacobians[:, jacobian_body_id, :, self.right_joint_ids]
        root_pos_w = self.robot.data.root_pos_w
        root_quat_w = self.robot.data.root_quat_w
        wrist_pos_b, wrist_quat_b = subtract_frame_transforms(root_pos_w, root_quat_w, wrist_pos_w, wrist_quat_w)
        tcp_pos_b, tcp_quat_b = combine_frame_transforms(wrist_pos_b, wrist_quat_b, tcp_offset, None)
        target_tcp_pos_b, target_tcp_quat_b = subtract_frame_transforms(
            root_pos_w,
            root_quat_w,
            target_tcp_pos_w_t,
            target_tcp_quat_w_t,
        )
        base_rot_matrix = matrix_from_quat(quat_inv(root_quat_w))
        jacobian = body_jacobian.clone()
        jacobian[:, 0:3, :] = torch.bmm(base_rot_matrix, jacobian[:, 0:3, :])
        jacobian[:, 3:6, :] = torch.bmm(base_rot_matrix, jacobian[:, 3:6, :])
        jacobian[:, 0:3, :] += torch.bmm(-skew_symmetric_matrix(tcp_offset), jacobian[:, 3:6, :])
        jacobian = jacobian * self.jacobian_sign * self.direction_sign

        if use_pose_ik:
            pose_command = torch.cat((target_tcp_pos_b, target_tcp_quat_b), dim=1)
            self.pose_ik_controller.set_command(pose_command, ee_pos=tcp_pos_b, ee_quat=tcp_quat_b)
            raw_target_q_t = self.pose_ik_controller.compute(tcp_pos_b, tcp_quat_b, jacobian, current_q_t)
            _, rot_error_t = compute_pose_error(
                tcp_pos_b,
                tcp_quat_b,
                target_tcp_pos_b,
                target_tcp_quat_b,
                rot_error_type="axis_angle",
            )
            rot_error_axis_angle = rot_error_t[0].detach().cpu().numpy()
        else:
            self.ik_controller.set_command(target_tcp_pos_b, ee_pos=tcp_pos_b, ee_quat=tcp_quat_b)
            raw_target_q_t = self.ik_controller.compute(tcp_pos_b, tcp_quat_b, jacobian, current_q_t)
        dq = (raw_target_q_t - current_q_t).clamp(-self.max_joint_delta, self.max_joint_delta)
        target_q_t = self.clamp_right_arm_q(current_q_t + dq)
        predicted_tcp_delta_b = (jacobian[:, 0:3, :] @ dq.unsqueeze(-1)).squeeze(-1)
        predicted_tcp_delta = matrix_from_quat(root_quat_w) @ predicted_tcp_delta_b.unsqueeze(-1)
        predicted_tcp_delta = predicted_tcp_delta.squeeze(-1)
        step_error_b = target_tcp_pos_b - tcp_pos_b
        step_error_w = matrix_from_quat(root_quat_w) @ step_error_b.unsqueeze(-1)
        step_error_w = step_error_w.squeeze(-1)
        step_norm = torch.linalg.norm(step_error_w, dim=1, keepdim=True).clamp_min(1e-6)
        step_error_w = step_error_w * torch.clamp(self.max_cart_step / step_norm, max=1.0)

        right_q_np = target_q_t[0].detach().cpu().numpy()
        desired = action.copy()
        desired[ACTION_SLICES.right_arm] = right_q_np
        desired[ACTION_SLICES.right_hand] = np.asarray(hand_values, dtype=np.float32)
        debug = self._make_debug(
            block_pos=block_pos,
            target_tcp_pos=target_tcp_pos,
            current_tcp_pos=current_tcp_pos,
            target_tcp_quat=target_tcp_quat,
            current_tcp_quat=current_tcp_quat,
            tcp_error=tcp_error_w,
            rot_error_axis_angle=rot_error_axis_angle,
            tcp_dist=tcp_dist,
            target_wrist_pos=target_wrist_pos_w[0].detach().cpu().numpy(),
            offset_world=offset_world,
            offset_frame=offset_frame,
            step_error_world=step_error_w[0].detach().cpu().numpy(),
            predicted_tcp_delta=predicted_tcp_delta[0].detach().cpu().numpy(),
            joint_delta=(target_q_t - current_q_t)[0].detach().cpu().numpy(),
            jacobian_body_row=jacobian_body_id,
            actual_delta_world=actual_delta,
            actual_progress=actual_progress,
            held_for_safety=False,
        )
        self._last_tcp_pos = current_tcp_pos.copy()
        self._last_tcp_error = tcp_error_w.copy()
        self._last_predicted_tcp_delta = predicted_tcp_delta[0].detach().cpu().numpy()
        return desired, debug, right_q_np, current_q


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
