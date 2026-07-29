#!/usr/bin/env python
"""Continuous S4 joint-angle debug entry.

This is a thin wrapper around ``03_record_physics_dataset.py --continuous`` so
the run.sh command has a clear name.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


SCRIPT = Path(__file__).with_name("03_record_physics_dataset.py")

if "--keyboard-jog" not in sys.argv and "--headless" not in sys.argv:
    sys.argv.append("--keyboard-jog")

runpy.run_path(str(SCRIPT), run_name="__main__")
