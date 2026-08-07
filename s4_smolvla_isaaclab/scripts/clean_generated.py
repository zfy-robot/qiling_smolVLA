#!/usr/bin/env python3
"""Remove generated local datasets and training outputs."""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("S4_DATA_ROOT", PROJECT_ROOT / "datasets"))
OUTPUT_ROOT = Path(os.environ.get("S4_OUTPUT_ROOT", PROJECT_ROOT / "outputs"))
DEFAULT_TARGETS = {
    "staging": DATA_ROOT / "staging",
    "lerobot": DATA_ROOT / "lerobot_data",
    "train": OUTPUT_ROOT / "train",
    "eval": OUTPUT_ROOT / "eval",
}
OPTIONAL_TARGETS = {
    "cache": Path(os.environ.get("S4_CACHE_ROOT", PROJECT_ROOT / ".cache")),
}


def remove_path(path: Path, dry_run: bool) -> None:
    if not path.exists():
        print(f"[CLEAN] skip missing {path}")
        return
    if dry_run:
        print(f"[CLEAN] would remove {path}")
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"[CLEAN] removed {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean generated S4 SmolVLA datasets/checkpoints.")
    parser.add_argument("--yes", action="store_true", help="Actually delete files. Without this, only prints targets.")
    parser.add_argument("--dry-run", action="store_true", help="Print targets without deleting.")
    parser.add_argument("--cache", action="store_true", help="Also remove local HuggingFace/cache files.")
    args = parser.parse_args()

    dry_run = args.dry_run or not args.yes
    if dry_run:
        print("[CLEAN] dry run; pass --yes to delete.")

    targets = dict(DEFAULT_TARGETS)
    if args.cache:
        targets.update(OPTIONAL_TARGETS)

    for path in targets.values():
        remove_path(path, dry_run=dry_run)

    if not dry_run:
        (DATA_ROOT / "staging").mkdir(parents=True, exist_ok=True)
        (DATA_ROOT / "lerobot_data").mkdir(parents=True, exist_ok=True)
        (OUTPUT_ROOT / "train").mkdir(parents=True, exist_ok=True)
        (OUTPUT_ROOT / "eval").mkdir(parents=True, exist_ok=True)
        print("[CLEAN] recreated empty generated-data directories.")


if __name__ == "__main__":
    main()
