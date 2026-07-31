"""Right-hand blue-cylinder-to-plate task specification."""

from __future__ import annotations

from pathlib import Path

from .base import TaskDataContract, TaskModuleSpec


PROJECT_ROOT = Path(__file__).resolve().parents[1]

TASK_ID = "right_blue_cylinder_plate"
TASK_DESCRIPTION = "Use the right hand to put the blue cylinder into the plate."

TASK_SPEC = TaskModuleSpec(
    task_id=TASK_ID,
    name="S4 right hand blue cylinder into plate",
    description=TASK_DESCRIPTION,
    dataset_config=PROJECT_ROOT / "configs" / "tasks" / "right_blue_cylinder_plate.dataset.json",
    train_config=PROJECT_ROOT / "configs" / "tasks" / "right_blue_cylinder_plate.smolvla.yaml",
    data=TaskDataContract(
        control_mode="right_only",
        state_dim=13,
        action_dim=13,
    ),
    scene_builder="s4_robot.simulation:build_scene",
    scripted_controller="tasks.right_blue_cylinder_plate_controller:RightBlueCylinderPlateController",
    notes=(
        "Current validated task. It records full debug HDF5 but converts only right_arm_7 + right_hand_6.",
        "Blue cylinder x/y is randomized during collection; red pill bottle is a fixed scene distractor.",
    ),
)
