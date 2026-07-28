#!/usr/bin/env python3
"""Convert local S4 HDF5 demonstrations into a LeRobotDataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.hdf5_schema import CHEST_FRONT_RGB
from data.lerobot_conversion import convert_hdf5_to_lerobot
from s4_pipeline.config import load_project_config


parser = argparse.ArgumentParser(description="Convert S4 bimanual HDF5 files to LeRobotDataset.")
parser.add_argument("--root-path", type=Path, default=None, help="HDF5 file or directory.")
parser.add_argument("--output-root", type=Path, default=None, help="Parent directory for LeRobot datasets.")
parser.add_argument("--repo-id", type=str, default=None)
parser.add_argument("--camera-path", action="append", default=None)
parser.add_argument("--robot-type", type=str, default="S4-Bimanual")
parser.add_argument("--overwrite", action="store_true", help="Delete an existing output dataset before converting.")
parser.add_argument(
    "extra_root_path_parts",
    nargs="*",
    help="Optional path fragments appended to --root-path, for accidental shell-split paths.",
)


def main() -> None:
    args = parser.parse_args()
    cfg = load_project_config()
    repo_id = args.repo_id or cfg.dataset.repo_id.split("/")[-1]
    root_path = args.root_path or cfg.dataset.staging_root
    if args.extra_root_path_parts:
        root_path = Path(root_path, *args.extra_root_path_parts)
    output_root = args.output_root or cfg.dataset.lerobot_root
    camera_paths = args.camera_path or [CHEST_FRONT_RGB]
    dataset_root = convert_hdf5_to_lerobot(
        root_path=root_path,
        output_root=output_root,
        repo_id=repo_id,
        task_description=cfg.dataset.task,
        robot_type=args.robot_type,
        camera_paths=camera_paths,
        fps=cfg.dataset.fps,
        overwrite=args.overwrite,
    )
    print(f"LeRobotDataset written to: {dataset_root}")


if __name__ == "__main__":
    main()
