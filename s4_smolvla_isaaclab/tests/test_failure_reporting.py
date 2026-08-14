from __future__ import annotations

import json

import pytest

from s4_pipeline.failure_reporting import CollectionFailureReporter
from scripts.dataset_check import _check_failure_summary


def failure_event(reason: str = "ik_timeout") -> dict[str, object]:
    return {
        "failure_type": "controller_failed",
        "reason": reason,
        "phase_name": "right_reach_can",
        "can_position_world_m": [0.52, -0.08, 1.16],
        "can_grid_cell": [2, 3],
    }


def test_failure_report_is_append_only_and_resume_safe(tmp_path) -> None:
    events = tmp_path / "failures.jsonl"
    summary = tmp_path / "summary.json"
    reporter = CollectionFailureReporter(events, summary, resume=False)
    reporter.record(failure_event())
    reporter.finalize(
        completed=False,
        accepted_episodes=4,
        target_episodes=20,
        skipped_grid_cells=[],
        hdf5_path=tmp_path / "data.hdf5",
    )

    resumed = CollectionFailureReporter(events, summary, resume=True)
    resumed.record(failure_event("grasp_unstable"))
    resumed.finalize(
        completed=True,
        accepted_episodes=20,
        target_episodes=20,
        skipped_grid_cells=[],
        hdf5_path=tmp_path / "data.hdf5",
    )

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["completed"] is True
    assert payload["failed_attempts"] == 2
    assert payload["failures_by_phase"] == {"right_reach_can": 2}
    assert payload["failures_by_reason"] == {"grasp_unstable": 1, "ik_timeout": 1}
    assert len(events.read_text(encoding="utf-8").splitlines()) == 2
    _check_failure_summary(
        summary,
        expected_episodes=20,
        max_failed_attempts=2,
        allow_skipped_grid_cells=False,
        expected_hdf5=tmp_path / "data.hdf5",
    )


def test_failure_summary_blocks_incomplete_or_skipped_collection(tmp_path) -> None:
    events = tmp_path / "failures.jsonl"
    summary = tmp_path / "summary.json"
    reporter = CollectionFailureReporter(events, summary, resume=False)
    reporter.record(failure_event())
    reporter.finalize(
        completed=True,
        accepted_episodes=20,
        target_episodes=20,
        skipped_grid_cells=[{"cell_x": 4, "cell_y": 1, "cycle": 0}],
    )
    with pytest.raises(ValueError, match="skipped 1 grid cell"):
        _check_failure_summary(
            summary,
            expected_episodes=20,
            max_failed_attempts=3,
            allow_skipped_grid_cells=False,
            expected_hdf5=None,
        )

    reporter.finalize(
        completed=False,
        accepted_episodes=19,
        target_episodes=20,
        skipped_grid_cells=[],
    )
    with pytest.raises(ValueError, match="did not complete"):
        _check_failure_summary(
            summary,
            expected_episodes=20,
            max_failed_attempts=3,
            allow_skipped_grid_cells=False,
            expected_hdf5=None,
        )
