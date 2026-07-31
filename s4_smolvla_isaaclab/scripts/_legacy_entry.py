"""Helpers for semantic script wrappers around legacy numbered entries."""

from __future__ import annotations

import runpy
from pathlib import Path


def run_legacy_script(filename: str) -> None:
    script_path = Path(__file__).resolve().parent / filename
    runpy.run_path(str(script_path), run_name="__main__")

