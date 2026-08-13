"""Shared drawer-task distractor contract for collection and rollout."""

from __future__ import annotations


DISTRACTOR_OBJECT_NAMES = (
    "distractor_master_chef_can",
    "distractor_mustard_bottle",
    "distractor_bleach_cleanser",
)

DISTRACTOR_ASSET_RELATIVE_PATHS = (
    "Isaac/Props/YCB/Axis_Aligned/002_master_chef_can.usd",
    "Isaac/Props/YCB/Axis_Aligned/006_mustard_bottle.usd",
    "Isaac/Props/YCB/Axis_Aligned/021_bleach_cleanser.usd",
)

# Three mutually separated cabinet-top regions in base_link XY coordinates.
# The first two are on the primary cabinet and the third is on the secondary
# cabinet, well away from the tomato-can grasp randomization region.
DEFAULT_DISTRACTOR_RANGES = (
    ((0.70, 1.00), (0.12, 0.30)),
    ((0.70, 1.00), (0.48, 0.66)),
    ((0.72, 1.00), (-0.68, -0.32)),
)

DEFAULT_DISTRACTOR_XY = (
    (0.85, 0.21),
    (0.85, 0.57),
    (0.86, -0.50),
)


def asset_contract() -> list[dict[str, str]]:
    """Return JSON-serializable names and portable asset-relative paths."""
    return [
        {"object_name": name, "asset_relative_path": path}
        for name, path in zip(DISTRACTOR_OBJECT_NAMES, DISTRACTOR_ASSET_RELATIVE_PATHS, strict=True)
    ]
