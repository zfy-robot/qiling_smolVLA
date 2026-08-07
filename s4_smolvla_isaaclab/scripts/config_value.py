#!/usr/bin/env python3
"""Print one expanded active-task configuration value for shell entrypoints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.config import load_project_config, load_training_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["project", "training"])
    parser.add_argument("key", help="Dot-separated key")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    value = load_training_config(args.config) if args.kind == "training" else load_project_config(args.config).raw
    for key in args.key.split("."):
        value = value[key]
    if isinstance(value, bool):
        print(str(value).lower())
    else:
        print(json.dumps(value) if isinstance(value, (dict, list)) else value)


if __name__ == "__main__":
    main()
