"""Pure retry decisions for scripted drawer dataset collection."""

from __future__ import annotations

from dataclasses import dataclass


GRASP_RETRY_PHASES = frozenset(
    {
        "right_pregrasp_can",
        "right_grasp_can",
        "right_settle_before_close",
        "right_close_hand",
        "right_hold_grasp",
        "right_lift_can",
    }
)


@dataclass(frozen=True)
class RetryDecision:
    retry_same_position: bool
    next_grasp_retry_count: int
    exhausted_grasp_position: bool


def decide_drawer_retry(
    phase_name: str,
    *,
    grasp_retry_count: int,
    max_grasp_retries_same_position: int,
) -> RetryDecision:
    """Retry grasp failures in-place; replace the point for all other failures.

    ``max_grasp_retries_same_position`` counts retries after the initial attempt.
    Once exhausted, another continuous point is sampled inside the same grid
    cell, so accepted demonstrations still cover every stratified cell.
    """

    phase = str(phase_name)
    retry_count = max(int(grasp_retry_count), 0)
    max_retries = max(int(max_grasp_retries_same_position), 0)
    if phase in GRASP_RETRY_PHASES and retry_count < max_retries:
        return RetryDecision(True, retry_count + 1, False)
    return RetryDecision(False, 0, phase in GRASP_RETRY_PHASES)
