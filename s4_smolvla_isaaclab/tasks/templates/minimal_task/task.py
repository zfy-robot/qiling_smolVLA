"""Minimal task registration template."""

from pathlib import Path

from tasks.base import TaskDataContract, TaskModuleSpec

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASK_ID = "replace_me"

TASK_SPEC = TaskModuleSpec(
    task_id=TASK_ID,
    name="Replace me",
    description="Replace this task text.",
    dataset_config=PROJECT_ROOT / "configs/tasks/replace_me.dataset.json",
    train_config=PROJECT_ROOT / "configs/tasks/replace_me.smolvla.yaml",
    data=TaskDataContract(
        control_mode="bimanual",
        state_dim=26,
        action_dim=26,
        schema_version="replace_me_v1",
    ),
    scene_builder="tasks.replace_me_scene:build_scene",
    scripted_controller="tasks.replace_me_controller:ReplaceMeController",
    scripted_config=PROJECT_ROOT / "configs/tasks/replace_me.scripted.yaml",
    rollout_kind="replace_me",
)
