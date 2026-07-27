#!/usr/bin/env python
"""Future local SmolVLA rollout entry for the S4 IsaacLab task."""

from __future__ import annotations

import argparse


parser = argparse.ArgumentParser(description="Evaluate a SmolVLA checkpoint in the local S4 IsaacLab scene.")
parser.add_argument("--checkpoint", required=True)
parser.add_argument("--episodes", type=int, default=10)


def main() -> None:
    args = parser.parse_args()
    raise SystemExit(
        "Local SmolVLA evaluation scaffold is installed but not implemented yet.\n"
        f"Checkpoint: {args.checkpoint}\n"
        f"Episodes: {args.episodes}\n"
        "Implement after HDF5 recording and LeRobotDataset conversion are validated."
    )


if __name__ == "__main__":
    main()

