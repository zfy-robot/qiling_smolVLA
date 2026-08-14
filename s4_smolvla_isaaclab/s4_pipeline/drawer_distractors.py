"""Shared drawer-task distractor contract for collection and rollout."""

from __future__ import annotations

import os


# Nominal grasp-can pose shared by scene construction, collection and rollout.
# Negative base_link Y is the robot's right-hand side. The task configuration
# defines the current IK-validated stratified sampling bounds around this pose.
GRASP_CAN_NOMINAL_POSITION = (0.54, -0.13, 1.16)
LEGACY_GRASP_CAN_NOMINAL_POSITION = (0.54, -0.08, 1.16)
GRASP_CAN_NOMINAL_Y_ENV = "S4_GRASP_CAN_NOMINAL_Y"

# Keep the original grasp-can dimensions. A scale-1.00 physical trial made the
# can about 10.19 mm longer and blocked drawer closure, so grasp geometry is
# improved through the TCP target instead of changing the object.
GRASP_CAN_SCALE = (1.0, 0.90, 1.0)
LEGACY_GRASP_CAN_SCALE = (1.0, 0.90, 1.0)
GRASP_CAN_SCALE_Y_ENV = "S4_GRASP_CAN_SCALE_Y"


def scene_grasp_can_nominal_position() -> tuple[float, float, float]:
    """Return the scene pose, allowing rollout to preserve legacy datasets."""
    y = float(os.environ.get(GRASP_CAN_NOMINAL_Y_ENV, GRASP_CAN_NOMINAL_POSITION[1]))
    return (GRASP_CAN_NOMINAL_POSITION[0], y, GRASP_CAN_NOMINAL_POSITION[2])


def scene_grasp_can_scale() -> tuple[float, float, float]:
    """Return the grasp-can scale, allowing rollout of legacy datasets."""
    scale_y = float(os.environ.get(GRASP_CAN_SCALE_Y_ENV, GRASP_CAN_SCALE[1]))
    return (GRASP_CAN_SCALE[0], scale_y, GRASP_CAN_SCALE[2])


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
