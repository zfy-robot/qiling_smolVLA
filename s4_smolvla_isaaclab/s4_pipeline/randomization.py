"""Deterministic randomization helpers shared by data-collection tools."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class StratifiedGridSample:
    """One uniformly sampled point inside a two-dimensional grid cell."""

    xy: np.ndarray
    cell_x: int
    cell_y: int
    cycle: int
    index_in_cycle: int


class StratifiedGrid2D:
    """Visit every cell once per shuffled cycle and sample inside each cell.

    Calling :meth:`sample` advances to the next cell. Collection code should
    therefore retain a returned sample while retrying a failed episode and
    request the next sample only after accepting the current episode.
    """

    def __init__(
        self,
        rng: np.random.Generator,
        *,
        x_range: tuple[float, float],
        y_range: tuple[float, float],
        cells_x: int = 5,
        cells_y: int = 5,
    ) -> None:
        self.rng = rng
        self.x_edges = self._edges("x_range", x_range, cells_x)
        self.y_edges = self._edges("y_range", y_range, cells_y)
        self.cells_x = int(cells_x)
        self.cells_y = int(cells_y)
        self._order = np.empty(0, dtype=np.int64)
        self._cursor = 0
        self._cycle = -1

    @staticmethod
    def _edges(name: str, value: tuple[float, float], cells: int) -> np.ndarray:
        if int(cells) < 1:
            raise ValueError(f"{name} grid cell count must be >= 1, got {cells}")
        low, high = (float(value[0]), float(value[1]))
        if not np.isfinite(low) or not np.isfinite(high) or low >= high:
            raise ValueError(f"{name} requires finite min < max, got {value}")
        return np.linspace(low, high, int(cells) + 1, dtype=np.float64)

    @property
    def cells_per_cycle(self) -> int:
        return self.cells_x * self.cells_y

    def _start_cycle(self) -> None:
        self._order = self.rng.permutation(self.cells_per_cycle)
        self._cursor = 0
        self._cycle += 1

    def sample(self) -> StratifiedGridSample:
        if self._cursor >= len(self._order):
            self._start_cycle()
        flat_index = int(self._order[self._cursor])
        index_in_cycle = self._cursor
        self._cursor += 1
        cell_y, cell_x = divmod(flat_index, self.cells_x)
        x = float(self.rng.uniform(self.x_edges[cell_x], self.x_edges[cell_x + 1]))
        y = float(self.rng.uniform(self.y_edges[cell_y], self.y_edges[cell_y + 1]))
        return StratifiedGridSample(
            xy=np.asarray([x, y], dtype=np.float32),
            cell_x=cell_x,
            cell_y=cell_y,
            cycle=self._cycle,
            index_in_cycle=index_in_cycle,
        )


def sample_xyz_range(rng: np.random.Generator, ranges: list[list[float]]) -> np.ndarray:
    """Sample an XYZ vector from three configured ``[min, max]`` ranges."""

    bounds = np.asarray(ranges, dtype=np.float64)
    if bounds.shape != (3, 2):
        raise ValueError(f"XYZ ranges must have shape (3, 2), got {bounds.shape}")
    if not np.all(np.isfinite(bounds)) or np.any(bounds[:, 0] > bounds[:, 1]):
        raise ValueError(f"XYZ ranges require finite min <= max, got {ranges}")
    return rng.uniform(bounds[:, 0], bounds[:, 1]).astype(np.float32)


def sample_separated_xy(
    rng: np.random.Generator,
    *,
    ranges: list[list[list[float]]],
    forbidden_xy: list[list[float]] | None = None,
    min_center_distance: float,
    max_attempts: int = 1000,
) -> np.ndarray:
    """Sample one XY point per rectangle while enforcing pairwise separation."""

    bounds = np.asarray(ranges, dtype=np.float64)
    if bounds.ndim != 3 or bounds.shape[1:] != (2, 2):
        raise ValueError(f"XY rectangle ranges must have shape (N, 2, 2), got {bounds.shape}")
    if not np.all(np.isfinite(bounds)) or np.any(bounds[:, :, 0] >= bounds[:, :, 1]):
        raise ValueError("Each XY rectangle requires finite min < max bounds")
    distance = float(min_center_distance)
    if not np.isfinite(distance) or distance <= 0.0:
        raise ValueError("min_center_distance must be finite and > 0")
    forbidden = np.asarray(forbidden_xy or [], dtype=np.float64).reshape(-1, 2)
    accepted: list[np.ndarray] = []
    for rectangle in bounds:
        for _ in range(int(max_attempts)):
            candidate = rng.uniform(rectangle[:, 0], rectangle[:, 1])
            occupied = [*forbidden, *accepted]
            if all(float(np.linalg.norm(candidate - other)) >= distance for other in occupied):
                accepted.append(candidate)
                break
        else:
            raise RuntimeError(
                "Could not sample separated XY positions; enlarge the ranges or reduce min_center_distance"
            )
    return np.asarray(accepted, dtype=np.float32)
