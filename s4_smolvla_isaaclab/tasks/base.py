"""Reusable task metadata contracts.

Task modules should describe the data/action contract and where task-specific
simulation logic lives. The recorder/eval/training pipeline can then stay
generic while scene construction and scripted collection remain swappable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TaskDataContract:
    """LeRobot-facing observation/action dimensions for one task."""

    control_mode: str
    state_dim: int
    action_dim: int
    camera_key: str = "observation.images.chest_front_rgb"


@dataclass(frozen=True)
class TaskModuleSpec:
    """Metadata for a trainable manipulation task."""

    task_id: str
    name: str
    description: str
    dataset_config: Path
    train_config: Path
    data: TaskDataContract
    scene_builder: str
    scripted_controller: str
    notes: tuple[str, ...] = field(default_factory=tuple)

