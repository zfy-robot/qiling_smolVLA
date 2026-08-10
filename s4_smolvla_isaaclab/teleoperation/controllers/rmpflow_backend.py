"""Two independent single-arm RMPflow policies for S4 Quest teleoperation."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from isaaclab.controllers.rmp_flow import RmpFlowController, RmpFlowControllerCfg

from s4_robot.arm_control import DEFAULT_TCP_OFFSET_WRIST
from teleoperation.config import RmpFlowArmConfig, RmpFlowConfig
from teleoperation.mapping import TcpPose, matrix_to_quat_wxyz, quat_wxyz_to_matrix


LEFT_ARM_JOINTS = (
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
)
RIGHT_ARM_JOINTS = tuple(name.replace("left_", "right_", 1) for name in LEFT_ARM_JOINTS)


def _pose_matrix(position: np.ndarray, quat_wxyz: np.ndarray) -> np.ndarray:
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = quat_wxyz_to_matrix(quat_wxyz)
    transform[:3, 3] = np.asarray(position, dtype=np.float64)
    return transform


class BimanualRmpFlowController:
    """Run one RMPflow instance per arm and return the established LA7+RA7 order.

    The two policies share the articulation state but deliberately do not model
    each other as obstacles. This is an explicit teleoperation design choice,
    not a full-body collision guarantee.
    """

    name = "rmpflow"

    def __init__(self, robot: Any, device: str, base_body_id: int, config: RmpFlowConfig):
        self._robot = robot
        self._device = device
        self._base_body_id = int(base_body_id)
        self._config = config
        self._robot_prim_path = str(robot.cfg.prim_path)
        self._left = self._make_policy(config.left)
        self._right = self._make_policy(config.right)
        self._left.initialize(self._robot_prim_path)
        self._right.initialize(self._robot_prim_path)
        self._validate_active_joints(self._left, LEFT_ARM_JOINTS, "left")
        self._validate_active_joints(self._right, RIGHT_ARM_JOINTS, "right")
        self._update_robot_base_pose()
        self._left.reset_idx()
        self._right.reset_idx()
        current = robot.data.joint_pos[0].detach().cpu().numpy()
        self._left_joint_ids = tuple(robot.joint_names.index(name) for name in LEFT_ARM_JOINTS)
        self._right_joint_ids = tuple(robot.joint_names.index(name) for name in RIGHT_ARM_JOINTS)
        self._left_target = current[list(self._left_joint_ids)].astype(np.float64).copy()
        self._right_target = current[list(self._right_joint_ids)].astype(np.float64).copy()
        self._step = 0
        print(
            "[TELEOP][RMPFLOW] ready: independent left/right policies, "
            f"simple arm spheres + torso cylinder, inter-arm collision disabled, "
            f"arm_update_every={config.update_every_n_steps} physics steps",
            flush=True,
        )

    def _make_policy(self, arm: RmpFlowArmConfig) -> RmpFlowController:
        cfg = RmpFlowControllerCfg(
            name=self._config.name,
            config_file=str(arm.policy_config_file),
            urdf_file=str(self._config.urdf_file),
            collision_file=str(arm.descriptor_file),
            frame_name=arm.frame_name,
            evaluations_per_frame=self._config.evaluations_per_frame,
            ignore_robot_state_updates=self._config.ignore_robot_state_updates,
        )
        return RmpFlowController(cfg, self._device)

    @staticmethod
    def _validate_active_joints(policy: RmpFlowController, expected: tuple[str, ...], side: str) -> None:
        actual = tuple(policy.active_dof_names)
        if actual != expected:
            raise RuntimeError(f"{side} RMPflow cspace mismatch: expected={expected}, actual={actual}")

    def _base_pose_world(self) -> tuple[np.ndarray, np.ndarray]:
        pose = self._robot.data.body_pose_w[0, self._base_body_id].detach().cpu().numpy()
        return pose[:3].astype(np.float64), pose[3:7].astype(np.float64)

    def _update_robot_base_pose(self) -> tuple[np.ndarray, np.ndarray]:
        position, quat_wxyz = self._base_pose_world()
        for wrapper in (self._left, self._right):
            wrapper.articulation_policies[0].motion_policy.set_robot_base_pose(position, quat_wxyz)
        return position, quat_wxyz

    @staticmethod
    def _tcp_base_to_wrist_base(target: TcpPose) -> np.ndarray:
        rotation = quat_wxyz_to_matrix(target.quat_wxyz)
        wrist_position = target.position - rotation @ np.asarray(DEFAULT_TCP_OFFSET_WRIST, dtype=np.float64)
        return _pose_matrix(wrist_position, target.quat_wxyz)

    def _world_wrist_command(
        self,
        target: TcpPose,
        base_position: np.ndarray,
        base_quat_wxyz: np.ndarray,
    ) -> torch.Tensor:
        world_base = _pose_matrix(base_position, base_quat_wxyz)
        world_wrist = world_base @ self._tcp_base_to_wrist_base(target)
        command = np.concatenate((world_wrist[:3, 3], matrix_to_quat_wxyz(world_wrist[:3, :3])))
        if not np.isfinite(command).all():
            raise RuntimeError(f"RMPflow received non-finite wrist target: {command}")
        return torch.tensor(command, dtype=torch.float32, device=self._device).view(1, 7)

    def set_posture_reference(self, joint_positions: np.ndarray) -> None:
        # RMPflow's cspace posture target is the descriptor default_q. A clutch
        # edge must not reset the dynamic policy or create a command jump.
        del joint_positions

    def compute(
        self,
        joint_positions: np.ndarray,
        dt: float,
        left_target: TcpPose,
        right_target: TcpPose,
    ) -> np.ndarray:
        del joint_positions
        base_position, base_quat_wxyz = self._update_robot_base_pose()
        interval = self._config.update_every_n_steps
        policy_dt = min(max(dt * interval, 1.0e-4), 0.05)
        if self._step % interval == 0:
            self._left_target = self._compute_side(
                self._left,
                self._world_wrist_command(left_target, base_position, base_quat_wxyz),
                policy_dt,
            )
        # Offset right-arm work when possible so one physics step does not pay
        # for both Lula policies. Both still update at the same mean rate.
        right_offset = 0 if interval == 1 else 1
        if self._step % interval == right_offset:
            self._right_target = self._compute_side(
                self._right,
                self._world_wrist_command(right_target, base_position, base_quat_wxyz),
                policy_dt,
            )
        self._step += 1
        result = np.concatenate((self._left_target, self._right_target)).astype(np.float64)
        if result.shape != (14,) or not np.isfinite(result).all():
            raise RuntimeError(f"RMPflow produced invalid LA7+RA7 targets: shape={result.shape} values={result}")
        return result

    @staticmethod
    def _compute_side(
        wrapper: RmpFlowController,
        command: torch.Tensor,
        controller_dt: float,
    ) -> np.ndarray:
        policy = wrapper.articulation_policies[0]
        motion_policy = policy.get_motion_policy()
        values = command[0].detach().cpu().numpy()
        motion_policy.set_end_effector_target(target_position=values[:3], target_orientation=values[3:7])
        action = policy.get_next_articulation_action(physics_dt=controller_dt)
        return np.asarray(action.joint_positions, dtype=np.float64).copy()

    def diagnostics(self) -> dict[str, str | float]:
        return {
            "backend": self.name,
            "substeps": float(self._config.evaluations_per_frame),
            "update_every_n_steps": float(self._config.update_every_n_steps),
            "inter_arm_collision": "disabled",
        }
