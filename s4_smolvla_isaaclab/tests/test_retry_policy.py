from s4_pipeline.retry_policy import decide_drawer_retry


def test_grasp_failure_retries_exact_position_three_times_then_replaces_point():
    for retry_count in range(3):
        decision = decide_drawer_retry(
            "right_grasp_can",
            grasp_retry_count=retry_count,
            max_grasp_retries_same_position=3,
        )
        assert decision.retry_same_position is True
        assert decision.next_grasp_retry_count == retry_count + 1
        assert decision.exhausted_grasp_position is False
    exhausted = decide_drawer_retry(
        "right_grasp_can",
        grasp_retry_count=3,
        max_grasp_retries_same_position=3,
    )
    assert exhausted.retry_same_position is False
    assert exhausted.next_grasp_retry_count == 0
    assert exhausted.exhausted_grasp_position is True


def test_non_grasp_failure_immediately_replaces_point_in_same_cell():
    decision = decide_drawer_retry(
        "right_open_hand",
        grasp_retry_count=2,
        max_grasp_retries_same_position=3,
    )
    assert decision.retry_same_position is False
    assert decision.next_grasp_retry_count == 0
    assert decision.exhausted_grasp_position is False
