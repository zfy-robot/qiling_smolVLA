"""Task metadata for the red/blue bimanual plate task."""

from __future__ import annotations

from dataclasses import dataclass


TASK_NAME = "s4_bimanual_red_blue_plate"
TASK_DESCRIPTION = (
    "Use the left hand to put the red block into the tray and the right hand "
    "to put the blue block into the tray."
)


@dataclass(frozen=True)
class SuccessThresholds:
    plate_radius_m: float = 0.13
    block_height_margin_m: float = 0.025
    max_block_speed_mps: float = 0.05


@dataclass(frozen=True)
class BimanualPlateTaskSpec:
    name: str = TASK_NAME
    description: str = TASK_DESCRIPTION
    success: SuccessThresholds = SuccessThresholds()
    action_dim: int = 26
    active_state_dim: int = 26


DEFAULT_TASK = BimanualPlateTaskSpec()

