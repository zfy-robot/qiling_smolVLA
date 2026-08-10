"""Compatibility wrapper for the pre-existing Pinocchio DLS teleop controller."""

from __future__ import annotations

from typing import Any

import numpy as np

from s4_robot.pink_bimanual_ik import PinkBimanualTcpController
from teleoperation.config import TeleopConfig
from teleoperation.mapping import TcpPose


class PinocchioTeleopController:
    name = "pinocchio"

    def __init__(self, robot: Any, device: str, config: TeleopConfig):
        self._orientation_weight = config.ik.orientation_weight
        self._controller = PinkBimanualTcpController(
            robot,
            device,
            posture_gain=config.ik.posture_gain,
            damping=config.ik.damping,
            max_joint_delta=config.ik.max_joint_delta_rad,
        )

    def set_posture_reference(self, joint_positions: np.ndarray) -> None:
        self._controller.set_posture_reference(joint_positions)

    def compute(
        self,
        joint_positions: np.ndarray,
        dt: float,
        left_target: TcpPose,
        right_target: TcpPose,
    ) -> np.ndarray:
        def payload(pose: TcpPose) -> dict[str, list[float] | float]:
            return {
                "pos": [float(value) for value in pose.position],
                "quat_wxyz": [float(value) for value in pose.quat_wxyz],
                "orientation_weight": float(self._orientation_weight),
            }

        return self._controller.compute(joint_positions, dt, payload(left_target), payload(right_target))

    def diagnostics(self) -> dict[str, str | float]:
        return {"backend": self.name}
