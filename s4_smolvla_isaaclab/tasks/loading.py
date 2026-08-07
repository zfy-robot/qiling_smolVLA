"""Generic task plugin loading helpers."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


def import_symbol(path: str) -> Any:
    module_name, symbol_name = path.split(":", 1)
    return getattr(importlib.import_module(module_name), symbol_name)


def load_yaml(path: Path) -> dict[str, Any]:
    import yaml

    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected YAML mapping: {path}")
    return value
