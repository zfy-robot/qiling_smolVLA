import numpy as np

from s4_pipeline.drawer_distractors import (
    GRASP_CAN_NOMINAL_POSITION,
    GRASP_CAN_NOMINAL_Y_ENV,
    scene_grasp_can_nominal_position,
)
from s4_pipeline.randomization import StratifiedGrid2D, sample_separated_xy, sample_xyz_range


def test_stratified_grid_covers_every_cell_before_repeating():
    sampler = StratifiedGrid2D(
        np.random.default_rng(42),
        x_range=(-0.05, 0.05),
        y_range=(-0.05, 0.05),
        cells_x=5,
        cells_y=5,
    )

    samples = [sampler.sample() for _ in range(25)]
    cells = {(sample.cell_x, sample.cell_y) for sample in samples}

    assert len(cells) == 25
    assert {sample.cycle for sample in samples} == {0}
    assert {sample.index_in_cycle for sample in samples} == set(range(25))
    assert all(-0.05 <= float(sample.xy[0]) <= 0.05 for sample in samples)
    assert all(-0.05 <= float(sample.xy[1]) <= 0.05 for sample in samples)
    assert sampler.sample().cycle == 1


def test_stratified_grid_is_seed_reproducible_and_samples_inside_cells():
    kwargs = dict(x_range=(-0.05, 0.05), y_range=(-0.05, 0.05), cells_x=5, cells_y=5)
    a = StratifiedGrid2D(np.random.default_rng(7), **kwargs)
    b = StratifiedGrid2D(np.random.default_rng(7), **kwargs)

    for _ in range(50):
        sample_a = a.sample()
        sample_b = b.sample()
        np.testing.assert_array_equal(sample_a.xy, sample_b.xy)
        assert (sample_a.cell_x, sample_a.cell_y, sample_a.cycle) == (
            sample_b.cell_x,
            sample_b.cell_y,
            sample_b.cycle,
        )
        x_low = -0.05 + sample_a.cell_x * 0.02
        y_low = -0.05 + sample_a.cell_y * 0.02
        assert x_low <= float(sample_a.xy[0]) <= x_low + 0.02
        assert y_low <= float(sample_a.xy[1]) <= y_low + 0.02


def test_xyz_range_is_bounded_and_seed_reproducible():
    ranges = [[-0.02, 0.02], [-0.02, 0.02], [-0.02, 0.02]]
    a = sample_xyz_range(np.random.default_rng(9), ranges)
    b = sample_xyz_range(np.random.default_rng(9), ranges)
    np.testing.assert_array_equal(a, b)
    assert np.all(a >= -0.02)
    assert np.all(a <= 0.02)


def test_separated_xy_stays_in_regions_and_avoids_task_can():
    ranges = [[[0.72, 1.02], [0.12, 0.65]], [[0.72, 1.02], [-0.70, -0.30]]]
    forbidden = [list(GRASP_CAN_NOMINAL_POSITION[:2])]
    points = sample_separated_xy(
        np.random.default_rng(42),
        ranges=ranges,
        forbidden_xy=forbidden,
        min_center_distance=0.14,
    )
    assert points.shape == (2, 2)
    for point, rectangle in zip(points, ranges, strict=True):
        assert rectangle[0][0] <= point[0] <= rectangle[0][1]
        assert rectangle[1][0] <= point[1] <= rectangle[1][1]
        assert np.linalg.norm(point - forbidden[0]) >= 0.14
    assert np.linalg.norm(points[0] - points[1]) >= 0.14


def test_scene_grasp_can_position_allows_legacy_rollout_override(monkeypatch):
    assert scene_grasp_can_nominal_position() == GRASP_CAN_NOMINAL_POSITION
    monkeypatch.setenv(GRASP_CAN_NOMINAL_Y_ENV, "-0.08")
    assert scene_grasp_can_nominal_position() == (0.54, -0.08, 1.16)


def test_grid_resamples_same_cell_and_restores_traversal_state():
    rng = np.random.default_rng(42)
    sampler = StratifiedGrid2D(rng, x_range=(-0.05, 0.05), y_range=(-0.05, 0.05), cells_x=5, cells_y=5)
    first = sampler.sample()
    traversal_state = sampler.state_dict()
    rng_state = rng.bit_generator.state
    alternate = sampler.resample_cell(first)
    assert (alternate.cell_x, alternate.cell_y) == (first.cell_x, first.cell_y)
    assert not np.array_equal(alternate.xy, first.xy)

    restored_rng = np.random.default_rng()
    restored_rng.bit_generator.state = rng_state
    restored = StratifiedGrid2D(
        restored_rng, x_range=(-0.05, 0.05), y_range=(-0.05, 0.05), cells_x=5, cells_y=5
    )
    restored.load_state_dict(traversal_state)
    np.testing.assert_array_equal(restored.resample_cell(first).xy, alternate.xy)
    assert restored.sample().index_in_cycle == 1
