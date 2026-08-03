"""Canonical HDF5 field names for S4 bimanual demonstrations."""

from __future__ import annotations

DEMO_PREFIX = "data/demo_"
PROCESSED_ACTIONS = "processed_actions"
FULL_JOINT_POS = "states/articulation/robot/joint_position"
ACTIVE_JOINT_POS = "obs/s4_active_joint_pos"
TASK_DESCRIPTION = "obs/task_description"
CHEST_FRONT_RGB = "obs/chest_front_rgb"
LEFT_EEF_POSE = "obs/left_arm_eef_pose"
RIGHT_EEF_POSE = "obs/right_arm_eef_pose"
RED_BLOCK_POSE = "states/rigid_object/red_block/root_pose"
BLUE_BLOCK_POSE = "states/rigid_object/blue_block/root_pose"
PLATE_POSE = "states/rigid_object/plate/root_pose"


REQUIRED_FOR_LEROBOT_CONVERSION = (
    PROCESSED_ACTIONS,
    FULL_JOINT_POS,
    CHEST_FRONT_RGB,
)
