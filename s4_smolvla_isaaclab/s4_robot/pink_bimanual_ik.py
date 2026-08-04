"""Pinocchio IK helper for interactive bimanual TCP debugging.

This module intentionally avoids Pink's ``Configuration`` and Isaac Lab's
``PinkIKController`` wrapper. In this IsaacSim process, several Pinocchio C++
vector return values fail Python conversion (``std::vector<string/int/bool>``).
The implementation below only uses scalar lookup APIs, frame placements and
Jacobians, then solves a damped least-squares IK step in NumPy.
"""

from __future__ import annotations

import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

from .s4_robot_cfg import DEFAULT_POSE, LEFT_ARM_JOINTS, RIGHT_ARM_JOINTS, URDF_PATH


DEFAULT_TCP_OFFSET_WRIST = np.array([0.0, 0.0, -0.10], dtype=np.float32)


def _prefer_cmeel_pinocchio_path() -> None:
    """Put cmeel's Python path before ROS Humble's Python 3.10 Pinocchio path."""
    cmeel = Path("/home/zfy/miniconda3/envs/env_isaaclab/lib/python3.11/site-packages/cmeel.prefix")
    site = cmeel / "lib/python3.11/site-packages"
    if site.is_dir():
        site_s = str(site)
        if site_s in sys.path:
            sys.path.remove(site_s)
        sys.path.insert(0, site_s)


def quat_wxyz_to_matrix(quat: np.ndarray) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64)
    norm = np.linalg.norm(q)
    if norm < 1.0e-8:
        return np.eye(3, dtype=np.float64)
    w, x, y, z = q / norm
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def quat_wxyz_from_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return np.array(
        [
            cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
        ],
        dtype=np.float32,
    )


def movable_urdf_joint_names() -> list[str]:
    root = ET.parse(str(URDF_PATH)).getroot()
    names: list[str] = []
    for joint in root.iter("joint"):
        joint_type = joint.get("type", "")
        name = joint.get("name")
        if name and joint_type != "fixed":
            names.append(name)
    return names


class PinkBimanualTcpController:
    """Damped least-squares Pinocchio solver for left/right wrist frames."""

    def __init__(
        self,
        robot,
        device: str,
        *,
        posture_gain: float = 0.30,
        damping: float = 0.08,
        max_joint_delta: float = 0.025,
    ):
        _prefer_cmeel_pinocchio_path()

        import pinocchio as pin

        self.pin = pin
        self.left_frame = "left_wrist_yaw_link"
        self.right_frame = "right_wrist_yaw_link"
        self.isaac_order_joint_names = LEFT_ARM_JOINTS + RIGHT_ARM_JOINTS
        self.isaac_order_joint_ids = [robot.joint_names.index(name) for name in self.isaac_order_joint_names]
        self.robot_joint_names = list(robot.joint_names)

        self.full_model = pin.buildModelFromUrdf(str(URDF_PATH.resolve()))
        self.full_data = self.full_model.createData()
        self.full_q0 = np.asarray(pin.neutral(self.full_model), dtype=np.float64)
        self.full_joint_names = movable_urdf_joint_names()
        # This robot is fixed-base and all non-fixed joints are 1-DoF. Avoid
        # accessing Pinocchio vector attributes such as model.names/model.idx_qs,
        # which can fail inside IsaacSim's already-loaded C++ bindings. For this
        # model, q index equals Pinocchio joint id minus the universe joint.
        self.pin_name_to_q_index: dict[str, int] = {}
        for name in self.full_joint_names:
            joint_id = int(self.full_model.getJointId(name))
            q_index = joint_id - 1
            if 0 <= q_index < self.full_q0.shape[0]:
                self.pin_name_to_q_index[name] = q_index

        missing = [name for name in self.isaac_order_joint_names if name not in self.pin_name_to_q_index]
        if missing:
            raise RuntimeError(f"TCP IK URDF missing controlled joints: {missing}")
        for frame in (self.left_frame, self.right_frame):
            if not self.full_model.existFrame(frame):
                raise RuntimeError(f"TCP IK URDF missing frame: {frame}")

        self.controlled_q_indices = np.asarray(
            [self.pin_name_to_q_index[name] for name in self.isaac_order_joint_names],
            dtype=np.int64,
        )
        self.home_controlled = np.asarray(
            [DEFAULT_POSE[name] for name in self.isaac_order_joint_names],
            dtype=np.float64,
        )
        self.posture_reference_controlled = self.home_controlled.copy()
        self.lower_controlled = np.asarray(self.full_model.lowerPositionLimit, dtype=np.float64)[
            self.controlled_q_indices
        ]
        self.upper_controlled = np.asarray(self.full_model.upperPositionLimit, dtype=np.float64)[
            self.controlled_q_indices
        ]
        self.frame_ids = {
            self.left_frame: int(self.full_model.getFrameId(self.left_frame)),
            self.right_frame: int(self.full_model.getFrameId(self.right_frame)),
        }
        self.position_gain = 1.0
        self.orientation_gain = 0.35
        self.damping = float(damping)
        self.max_joint_delta = float(max_joint_delta)
        self.posture_gain = float(posture_gain)
        print(
            "[PINK] fallback Pinocchio DLS solver ready "
            f"pinocchio={getattr(pin, '__file__', '<built-in>')} "
            f"controlled_order={self.isaac_order_joint_names} "
            f"damping={self.damping:.3f} max_joint_delta={self.max_joint_delta:.3f} "
            f"nullspace_posture_gain={self.posture_gain:.3f}",
            flush=True,
        )

    def set_posture_reference(self, curr_joint_pos: np.ndarray) -> None:
        """Keep the IK on the current continuous joint branch for a new phase."""
        curr = np.asarray(curr_joint_pos, dtype=np.float64)
        if curr.shape == (len(self.robot_joint_names),):
            full_q = self._full_q_from_isaac(curr)
            reference = full_q[self.controlled_q_indices]
        elif curr.shape == (len(self.controlled_q_indices),):
            reference = curr
        else:
            raise ValueError(
                "IK posture reference must contain either all robot joints or the 14 controlled arm joints, "
                f"got shape={curr.shape}"
            )
        self.posture_reference_controlled = np.clip(
            reference,
            self.lower_controlled + 1.0e-3,
            self.upper_controlled - 1.0e-3,
        )

    def _full_q_from_isaac(self, curr_joint_pos: np.ndarray) -> np.ndarray:
        full_q = self.full_q0.copy()
        curr = np.asarray(curr_joint_pos, dtype=np.float64)
        for isaac_i, name in enumerate(self.robot_joint_names):
            q_i = self.pin_name_to_q_index.get(name)
            if q_i is not None and isaac_i < curr.shape[0]:
                full_q[q_i] = curr[isaac_i]
        return full_q

    @staticmethod
    def _skew(vector: np.ndarray) -> np.ndarray:
        x, y, z = np.asarray(vector, dtype=np.float64)
        return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=np.float64)

    def _append_frame_task(
        self,
        rows: list[np.ndarray],
        errors: list[np.ndarray],
        frame_name: str,
        pose: dict[str, list[float]],
    ) -> None:
        target_pos = np.asarray(pose["pos"], dtype=np.float64)
        target_rot = quat_wxyz_to_matrix(np.asarray(pose["quat_wxyz"], dtype=np.float64))
        orientation_weight = float(np.clip(pose.get("orientation_weight", 1.0), 0.0, 1.0))
        frame_id = self.frame_ids[frame_name]
        current = self.full_data.oMf[frame_id]
        current_rot = np.asarray(current.rotation, dtype=np.float64)
        tcp_offset_world = current_rot @ np.asarray(DEFAULT_TCP_OFFSET_WRIST, dtype=np.float64)
        current_tcp_pos = np.asarray(current.translation, dtype=np.float64) + tcp_offset_world
        pos_err = (target_pos - current_tcp_pos) * self.position_gain
        rot_err = self.pin.log3(target_rot @ np.asarray(current.rotation, dtype=np.float64).T) * self.orientation_gain
        jac = self.pin.getFrameJacobian(
            self.full_model,
            self.full_data,
            frame_id,
            self.pin.ReferenceFrame.LOCAL_WORLD_ALIGNED,
        )
        tcp_jac = np.asarray(jac, dtype=np.float64)[:, self.controlled_q_indices].copy()
        # Shift the wrist Jacobian to the actual TCP point. This keeps TCP
        # position control correct even when the requested wrist orientation is
        # only a soft, partially reachable objective.
        tcp_jac[:3] -= self._skew(tcp_offset_world) @ tcp_jac[3:]
        weights = np.array([1.0, 1.0, 1.0, orientation_weight, orientation_weight, orientation_weight])
        rows.append(weights[:, None] * tcp_jac)
        errors.append(weights * np.concatenate([pos_err, rot_err]))

    def compute(
        self,
        curr_joint_pos: np.ndarray,
        dt: float,
        left_pose_base: dict[str, list[float]] | None,
        right_pose_base: dict[str, list[float]] | None,
    ) -> np.ndarray:
        full_q = self._full_q_from_isaac(curr_joint_pos)
        self.pin.computeJointJacobians(self.full_model, self.full_data, full_q)
        self.pin.updateFramePlacements(self.full_model, self.full_data)

        rows: list[np.ndarray] = []
        errors: list[np.ndarray] = []
        if left_pose_base is not None:
            self._append_frame_task(rows, errors, self.left_frame, left_pose_base)
        if right_pose_base is not None:
            self._append_frame_task(rows, errors, self.right_frame, right_pose_base)

        current_controlled = full_q[self.controlled_q_indices].copy()
        if not rows:
            return current_controlled.astype(np.float32)

        jac = np.vstack(rows)
        err = np.concatenate(errors)
        lhs = jac @ jac.T + (self.damping**2) * np.eye(jac.shape[0], dtype=np.float64)
        jac_pinv = jac.T @ np.linalg.solve(lhs, np.eye(jac.shape[0], dtype=np.float64))
        dq_task = jac_pinv @ err
        if self.posture_gain > 0.0:
            # The damped inverse used for the task is deliberately not used
            # here: I - J_damped# J leaks posture motion into the TCP task.
            # A Moore-Penrose projector keeps the posture term in the actual
            # numerical null space and preserves the current phase's IK branch.
            jac_pinv_projector = np.linalg.pinv(jac, rcond=1.0e-4)
            null_projector = np.eye(jac.shape[1], dtype=np.float64) - jac_pinv_projector @ jac
            posture_error = self.posture_reference_controlled - current_controlled
            dq_posture = null_projector @ (self.posture_gain * posture_error)
            dq = dq_task + dq_posture
        else:
            dq = dq_task
        # Preserve the DLS direction when limiting a step. Element-wise
        # clipping changes the joint-space direction and can create wrist arcs.
        max_abs_delta = float(np.max(np.abs(dq)))
        if max_abs_delta > self.max_joint_delta:
            dq *= self.max_joint_delta / max_abs_delta
        q_next = np.clip(
            current_controlled + dq,
            self.lower_controlled + 1.0e-3,
            self.upper_controlled - 1.0e-3,
        )
        return q_next.astype(np.float32)
