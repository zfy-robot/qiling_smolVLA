"""Task registry for reusable S4 SmolVLA IsaacLab tasks."""

from __future__ import annotations

from .base import TaskDataContract, TaskModuleSpec
from .drawer_insert_close import TASK_SPEC as DRAWER_INSERT_CLOSE
from .right_blue_cylinder_plate import TASK_SPEC as RIGHT_BLUE_CYLINDER_PLATE


TASK_REGISTRY: dict[str, TaskModuleSpec] = {
    RIGHT_BLUE_CYLINDER_PLATE.task_id: RIGHT_BLUE_CYLINDER_PLATE,
    DRAWER_INSERT_CLOSE.task_id: DRAWER_INSERT_CLOSE,
}


def get_task_spec(task_id: str) -> TaskModuleSpec:
    try:
        return TASK_REGISTRY[task_id]
    except KeyError as exc:
        available = ", ".join(sorted(TASK_REGISTRY))
        raise KeyError(f"Unknown task_id={task_id!r}. Available tasks: {available}") from exc


__all__ = [
    "DRAWER_INSERT_CLOSE",
    "RIGHT_BLUE_CYLINDER_PLATE",
    "TASK_REGISTRY",
    "TaskDataContract",
    "TaskModuleSpec",
    "get_task_spec",
]
