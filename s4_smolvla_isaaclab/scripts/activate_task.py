#!/usr/bin/env python3
"""Activate a registered task by copying its configs into the stable paths."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.paths import DATASET_CONFIG_PATH, SMOLVLA_CONFIG_PATH
from tasks import TASK_REGISTRY, get_task_spec


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate a registered task config.")
    parser.add_argument("task_id", choices=sorted(TASK_REGISTRY))
    parser.add_argument("--dry-run", action="store_true", help="Print the files that would be copied.")
    args = parser.parse_args()

    spec = get_task_spec(args.task_id)
    copies = [
        (spec.dataset_config, DATASET_CONFIG_PATH),
        (spec.train_config, SMOLVLA_CONFIG_PATH),
    ]
    for src, dst in copies:
        if not src.is_file():
            raise FileNotFoundError(f"Task config does not exist: {src}")
        print(f"{src} -> {dst}")
        if not args.dry_run:
            shutil.copyfile(src, dst)

    if args.dry_run:
        print(f"[DRY-RUN] task not activated: {args.task_id}")
    else:
        print(f"[OK] active task: {args.task_id}")


if __name__ == "__main__":
    main()

