"""Drawer open-insert-close task placeholder.

This is the next task target. It intentionally registers the task contract and
expected module boundaries before the drawer scene and scripted controller are
implemented.
"""

from __future__ import annotations

from pathlib import Path

from .base import TaskDataContract, TaskModuleSpec


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TASK_ID = "drawer_insert_close"
TASK_DESCRIPTION = "Open the drawer, place the object inside, and close the drawer."

TASK_SPEC = TaskModuleSpec(
    task_id=TASK_ID,
    name="S4 right hand drawer insert close",
    description=TASK_DESCRIPTION,
    dataset_config=PROJECT_ROOT / "configs" / "tasks" / "drawer_insert_close.dataset.json",
    train_config=PROJECT_ROOT / "configs" / "tasks" / "drawer_insert_close.smolvla.yaml",
    data=TaskDataContract(
        control_mode="right_only",
        state_dim=13,
        action_dim=13,
    ),
    scene_builder="tasks.drawer_insert_close_scene:build_scene",
    scripted_controller="tasks.drawer_insert_close_controller:DrawerInsertCloseController",
    notes=(
        "Planned task: load a drawer scene/object, pull drawer, insert object, close drawer.",
        "Keep conversion/training unchanged unless drawer/object state must be added to observation.state.",
    ),
)
