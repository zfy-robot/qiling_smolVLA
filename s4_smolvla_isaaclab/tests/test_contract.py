import numpy as np

from s4_robot.control_mapping import (
    ACTION_SLICES,
    BIMANUAL_ACTION_DIM,
    action_to_joint_targets,
    hand6_to_joint_targets,
)


def test_26d_layout_is_stable():
    assert BIMANUAL_ACTION_DIM == 26
    assert ACTION_SLICES.left_arm == slice(0, 7)
    assert ACTION_SLICES.left_hand == slice(7, 13)
    assert ACTION_SLICES.right_arm == slice(13, 20)
    assert ACTION_SLICES.right_hand == slice(20, 26)
    assert len(action_to_joint_targets(np.zeros(26, dtype=np.float32))) >= 26


def test_hand6_expands_mimic_joints():
    targets = hand6_to_joint_targets("rh", [0.5, 0.2, 0.3, 0.4, 0.5, 0.6])
    assert len(targets) == 11
    assert np.isclose(targets["rh_index_dip"], targets["rh_index_mcp_pitch"] * 0.89)
