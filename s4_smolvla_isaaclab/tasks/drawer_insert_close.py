"""Drawer open-insert-close task definition."""

from __future__ import annotations

from pathlib import Path

from .base import TaskDataContract, TaskModuleSpec


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TASK_ID = "drawer_insert_close"
TASK_DESCRIPTION = "Open the drawer, place the object inside, and close the drawer."

TASK_SPEC = TaskModuleSpec(
    task_id=TASK_ID,
    name="S4 bimanual drawer insert close",
    description=TASK_DESCRIPTION,
    dataset_config=PROJECT_ROOT / "configs" / "tasks" / "drawer_insert_close.dataset.json",
    train_config=PROJECT_ROOT / "configs" / "tasks" / "drawer_insert_close.smolvla.yaml",
    data=TaskDataContract(
        control_mode="bimanual",
        state_dim=26,
        action_dim=26,
        schema_version="s4_bimanual_v1",
    ),
    scene_builder="tasks.drawer_insert_close_scene:build_scene",
    scripted_controller="tasks.drawer_insert_close_controller:DrawerInsertCloseController",
    scripted_config=PROJECT_ROOT / "configs" / "tasks" / "drawer_insert_close.scripted.yaml",
    rollout_kind="drawer_insert_close",
    notes=(
        "Scripted data path: YAML phases -> bimanual TCP IK -> 26D action/state HDF5 -> LeRobot.",
        "Observation.state is left_arm_7 + left_hand_6 + right_arm_7 + right_hand_6.",
    ),
)
