#!/usr/bin/env python3
"""Select a task locally without modifying committed configuration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.paths import LOCAL_DIR
from tasks import TASK_REGISTRY, get_task_spec


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate a registered task for this checkout.")
    parser.add_argument("task_id", choices=sorted(TASK_REGISTRY))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    spec = get_task_spec(args.task_id)
    for path in (spec.dataset_config, spec.train_config):
        if not path.is_file():
            raise FileNotFoundError(f"Task config does not exist: {path}")
    target = LOCAL_DIR / "active_task"
    print(f"active task: {args.task_id}")
    print(f"dataset: {spec.dataset_config}")
    print(f"training: {spec.train_config}")
    if not args.dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args.task_id + "\n", encoding="utf-8")
        print(f"local selection: {target}")


if __name__ == "__main__":
    main()
