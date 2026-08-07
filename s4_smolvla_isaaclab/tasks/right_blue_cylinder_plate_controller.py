"""Current blue-cylinder scripted controller boundary.

The implemented state machine still lives in `scripts/record_dataset.py`
to preserve the validated collection path. New task work should not copy that
whole script; migrate task-specific phases behind this module instead.
"""

from __future__ import annotations


class RightBlueCylinderPlateController:
    """Marker class for the current validated scripted controller boundary."""

    implemented_in = "scripts/record_dataset.py"
