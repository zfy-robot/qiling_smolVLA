from __future__ import annotations

import numpy as np

from s4_pipeline.drawer_distractors import (
    GRASP_CAN_SCALE,
    GRASP_CAN_SCALE_Y_ENV,
    LEGACY_GRASP_CAN_SCALE,
    scene_grasp_can_scale,
)
from tasks.drawer_insert_close_controller import DrawerInsertCloseController, load_scripted_config


class _FakeTcpController:
    isaac_order_joint_ids = list(range(14))


def _anchors() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    quat = np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    return {
        "can": (np.asarray([0.54, -0.13, 0.18], dtype=np.float32), quat),
        "drawer_handle_initial": (np.asarray([0.44, 0.38, 0.05], dtype=np.float32), quat),
        "drawer_handle_open": (np.asarray([0.26, 0.38, 0.05], dtype=np.float32), quat),
        "drawer_handle_closed": (np.asarray([0.44, 0.38, 0.05], dtype=np.float32), quat),
    }


def test_original_can_scale_and_rollout_override(monkeypatch):
    assert GRASP_CAN_SCALE == (1.0, 0.90, 1.0)
    assert LEGACY_GRASP_CAN_SCALE == (1.0, 0.90, 1.0)
    assert scene_grasp_can_scale() == GRASP_CAN_SCALE
    monkeypatch.setenv(GRASP_CAN_SCALE_Y_ENV, "0.90")
    assert scene_grasp_can_scale() == LEGACY_GRASP_CAN_SCALE


def test_grasp_config_is_stationary_and_deterministic():
    cfg = load_scripted_config()
    assert cfg["randomization"]["can_xy"]["x_range"] == [-0.055, -0.005]
    assert cfg["randomization"]["can_xy"]["y_range"] == [-0.06, 0.02]
    assert cfg["randomization"]["can_xy"]["max_points_per_cell"] == 3
    assert cfg["randomization"]["can_xy"]["on_cell_exhausted"] == "abort"
    assert cfg["randomization"]["right_can_lift"]["enabled"] is False
    assert cfg["hands"]["right_open"][0] == 0.8
    assert cfg["hands"]["right_close"] == [1.0, 0.42, 0.85, 0.85, 0.85, 0.85]
    assert cfg["targets"]["right_can_grasp"]["offset"] == [-0.04, -0.025, 0.030]

    phases = {phase["name"]: phase for phase in cfg["phases"]}
    assert phases["right_grasp_can"]["tolerance"] == 0.012
    for name in (
        "right_pregrasp_can",
        "right_grasp_can",
        "right_settle_before_close",
        "right_close_hand",
        "right_hold_grasp",
    ):
        assert phases[name]["require_left_tcp_reached"] is False
        assert phases[name]["left"] == {"target": "left_drawer_open"}
    for name in ("right_settle_before_close", "right_close_hand", "right_hold_grasp"):
        assert phases[name]["hold_current_right_pose"] is True
    assert phases["right_settle_before_close"]["right_hand"] == "open"
    assert phases["right_settle_before_close"]["hold_seconds"] == 1.0
    assert phases["right_close_hand"]["right_hand"] == "close"
    assert phases["right_hold_grasp"]["right_hand"] == "close"


def test_hold_current_right_pose_freezes_phase_entry_tcp():
    controller = DrawerInsertCloseController(
        _FakeTcpController(),
        initial_action=np.zeros(26, dtype=np.float32),
        anchors=_anchors(),
    )
    phase_index = next(
        index for index, phase in enumerate(controller.phases) if phase.name == "right_close_hand"
    )
    controller.phase_index = phase_index
    measured_pos = np.asarray([0.47, -0.16, 0.22], dtype=np.float32)
    measured_quat = np.asarray([0.7, 0.0, -0.7, 0.0], dtype=np.float32)
    controller._prepare_current_phase(
        (np.zeros(3, dtype=np.float32), np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32)),
        (measured_pos, measured_quat),
        drawer_open_m=0.18,
    )
    np.testing.assert_allclose(controller.current_phase.right.pos, measured_pos)
    np.testing.assert_allclose(controller.current_phase.right.quat_wxyz, measured_quat)
