"""Control-space mapping for S4 bimanual manipulation.

The policy/control interface is intentionally smaller than the imported URDF:

    action/state = left arm 7 + left hand 6 + right arm 7 + right hand 6

Each O6 hand exposes six active control inputs in the URDF. The remaining
finger joints are mimic joints and can either be handled by the importer or by
this module when the simulator exposes them as independent joints.
"""

from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np

from .s4_robot_cfg import (
    ALL_DRIVE_JOINTS,
    LEFT_ARM_JOINTS,
    LEFT_HAND_JOINTS,
    RIGHT_ARM_JOINTS,
    RIGHT_HAND_JOINTS,
    get_default_joint_positions,
    get_joint_limits,
)


LEFT_HAND_MIMIC_MULTIPLIERS = {
    "lh_thumb_ip": ("lh_thumb_cmc_pitch", 2.29),
    "lh_index_dip": ("lh_index_mcp_pitch", 0.89),
    "lh_middle_dip": ("lh_middle_mcp_pitch", 0.89),
    "lh_ring_dip": ("lh_ring_mcp_pitch", 0.89),
    "lh_pinky_dip": ("lh_pinky_mcp_pitch", 0.89),
}

RIGHT_HAND_MIMIC_MULTIPLIERS = {
    "rh_thumb_ip": ("rh_thumb_cmc_pitch", 1.86),
    "rh_index_dip": ("rh_index_mcp_pitch", 0.89),
    "rh_middle_dip": ("rh_middle_mcp_pitch", 0.89),
    "rh_ring_dip": ("rh_ring_mcp_pitch", 0.89),
    "rh_pinky_dip": ("rh_pinky_mcp_pitch", 0.89),
}

LEFT_HAND_ALL_JOINTS = [
    "lh_thumb_cmc_yaw",
    "lh_thumb_cmc_pitch",
    "lh_thumb_ip",
    "lh_index_mcp_pitch",
    "lh_index_dip",
    "lh_middle_mcp_pitch",
    "lh_middle_dip",
    "lh_ring_mcp_pitch",
    "lh_ring_dip",
    "lh_pinky_mcp_pitch",
    "lh_pinky_dip",
]

RIGHT_HAND_ALL_JOINTS = [
    "rh_thumb_cmc_yaw",
    "rh_thumb_cmc_pitch",
    "rh_thumb_ip",
    "rh_index_mcp_pitch",
    "rh_index_dip",
    "rh_middle_mcp_pitch",
    "rh_middle_dip",
    "rh_ring_mcp_pitch",
    "rh_ring_dip",
    "rh_pinky_mcp_pitch",
    "rh_pinky_dip",
]

BIMANUAL_ARM_HAND_JOINTS = (
    LEFT_ARM_JOINTS + LEFT_HAND_JOINTS + RIGHT_ARM_JOINTS + RIGHT_HAND_JOINTS
)
BIMANUAL_ACTION_DIM = len(BIMANUAL_ARM_HAND_JOINTS)


class BimanualActionSlices:
    left_arm = slice(0, 7)
    left_hand = slice(7, 13)
    right_arm = slice(13, 20)
    right_hand = slice(20, 26)


ACTION_SLICES = BimanualActionSlices()


def bimanual_default_action() -> np.ndarray:
    """Return the default bimanual control vector in policy order."""
    defaults = dict(zip(ALL_DRIVE_JOINTS, get_default_joint_positions(), strict=True))
    return np.asarray([defaults[j] for j in BIMANUAL_ARM_HAND_JOINTS], dtype=np.float32)


def clip_joint_targets(targets: Mapping[str, float]) -> dict[str, float]:
    """Clip joint targets to URDF limits where available."""
    limits = get_joint_limits()
    clipped: dict[str, float] = {}
    for name, value in targets.items():
        if name in limits:
            lo = limits[name]["lower"]
            hi = limits[name]["upper"]
            clipped[name] = float(np.clip(value, lo, hi))
        else:
            clipped[name] = float(value)
    return clipped


def hand6_to_joint_targets(prefix: str, hand_action: Sequence[float], include_mimic: bool = True) -> dict[str, float]:
    """Map one O6 hand's six active controls to URDF finger joint targets.

    Args:
        prefix: Either ``"lh"`` or ``"rh"``.
        hand_action: Six active controls in the order used by ``LEFT_HAND_JOINTS``
            or ``RIGHT_HAND_JOINTS``.
        include_mimic: If true, also emit targets for exposed mimic joints.
            This is useful when an importer materializes mimic joints as normal
            DOFs. If the importer handles mimic internally, these extra targets
            are ignored by name filtering later.
    """
    if prefix not in {"lh", "rh"}:
        raise ValueError(f"prefix must be 'lh' or 'rh', got {prefix!r}")
    values = np.asarray(hand_action, dtype=np.float32)
    if values.shape != (6,):
        raise ValueError(f"hand_action must have shape (6,), got {values.shape}")

    active = LEFT_HAND_JOINTS if prefix == "lh" else RIGHT_HAND_JOINTS
    targets = {name: float(value) for name, value in zip(active, values, strict=True)}

    if include_mimic:
        mimic = LEFT_HAND_MIMIC_MULTIPLIERS if prefix == "lh" else RIGHT_HAND_MIMIC_MULTIPLIERS
        for mimic_joint, (source_joint, multiplier) in mimic.items():
            targets[mimic_joint] = targets[source_joint] * multiplier

    return clip_joint_targets(targets)


def action_to_joint_targets(action: Sequence[float], include_mimic: bool = True) -> dict[str, float]:
    """Map a 26-D bimanual action vector to named joint targets."""
    action_np = np.asarray(action, dtype=np.float32)
    if action_np.shape != (BIMANUAL_ACTION_DIM,):
        raise ValueError(f"action must have shape ({BIMANUAL_ACTION_DIM},), got {action_np.shape}")

    targets: dict[str, float] = {}
    targets.update(
        {name: float(value) for name, value in zip(LEFT_ARM_JOINTS, action_np[ACTION_SLICES.left_arm], strict=True)}
    )
    targets.update(hand6_to_joint_targets("lh", action_np[ACTION_SLICES.left_hand], include_mimic))
    targets.update(
        {name: float(value) for name, value in zip(RIGHT_ARM_JOINTS, action_np[ACTION_SLICES.right_arm], strict=True)}
    )
    targets.update(hand6_to_joint_targets("rh", action_np[ACTION_SLICES.right_hand], include_mimic))
    return clip_joint_targets(targets)


def make_full_joint_target(
    action: Sequence[float],
    robot_joint_names: Sequence[str],
    default_by_robot_order: Sequence[float] | None = None,
    include_mimic: bool = True,
) -> np.ndarray:
    """Create a full simulator joint target array in ``robot_joint_names`` order."""
    if default_by_robot_order is None:
        target = np.zeros(len(robot_joint_names), dtype=np.float32)
        defaults = dict(zip(ALL_DRIVE_JOINTS, get_default_joint_positions(), strict=True))
        for i, name in enumerate(robot_joint_names):
            target[i] = defaults.get(name, 0.0)
    else:
        target = np.asarray(default_by_robot_order, dtype=np.float32).copy()
        if target.shape != (len(robot_joint_names),):
            raise ValueError(
                f"default_by_robot_order must have shape ({len(robot_joint_names)},), got {target.shape}"
            )

    named_targets = action_to_joint_targets(action, include_mimic=include_mimic)
    for i, name in enumerate(robot_joint_names):
        if name in named_targets:
            target[i] = named_targets[name]
    return target


def extract_bimanual_state(joint_pos: Sequence[float], robot_joint_names: Sequence[str]) -> np.ndarray:
    """Extract the 26-D policy state from simulator joint positions."""
    q = np.asarray(joint_pos, dtype=np.float32)
    if q.shape != (len(robot_joint_names),):
        raise ValueError(f"joint_pos must have shape ({len(robot_joint_names)},), got {q.shape}")
    name_to_value = {name: q[i] for i, name in enumerate(robot_joint_names)}
    defaults = dict(zip(ALL_DRIVE_JOINTS, get_default_joint_positions(), strict=True))
    state = [name_to_value.get(name, defaults.get(name, 0.0)) for name in BIMANUAL_ARM_HAND_JOINTS]
    return np.asarray(state, dtype=np.float32)


def format_action_layout() -> str:
    """Return a human-readable action layout for logging."""
    lines = [f"Bimanual action dim: {BIMANUAL_ACTION_DIM}"]
    for i, name in enumerate(BIMANUAL_ARM_HAND_JOINTS):
        lines.append(f"  [{i:02d}] {name}")
    return "\n".join(lines)
