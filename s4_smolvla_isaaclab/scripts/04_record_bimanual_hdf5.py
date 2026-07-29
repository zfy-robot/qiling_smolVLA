#!/usr/bin/env python
"""Record scripted S4 grasp/place episodes to the project HDF5 schema."""

from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.config import load_project_config


parser = argparse.ArgumentParser(description="Record S4 scripted grasp demos to HDF5.")
parser.add_argument("--output", type=Path, default=None)
parser.add_argument("--num-episodes", type=int, default=1)
parser.add_argument("--block", choices=["red", "blue"], default="blue")
parser.add_argument("--record-every-n", type=int, default=6)
parser.add_argument(
    "--episode-timeout-s",
    type=float,
    default=500.0,
    help="Discard and retry an episode if scripted collection exceeds this wall-clock timeout.",
)
parser.add_argument("--camera-width", type=int, default=320)
parser.add_argument("--camera-height", type=int, default=240)
parser.add_argument(
    "--no-render",
    action="store_true",
    help="Run IsaacLab headless while still recording camera frames, for faster batch collection.",
)
parser.add_argument(
    "--randomize-blue-xy",
    type=float,
    default=0.03,
    help="Per-episode uniform randomization range for the blue cylinder x/y position in meters.",
)
parser.add_argument("--random-seed", type=int, default=42)


def main() -> None:
    args, passthrough = parser.parse_known_args()
    cfg = load_project_config()
    output = args.output or cfg.dataset.staging_root / "s4_right_blue_cylinder_plate_scripted.hdf5"
    sim_script = Path(__file__).with_name("03_record_physics_dataset.py")
    sys.argv = [
        str(sim_script),
        "--record-output",
        str(output),
        "--record-episodes",
        str(max(int(args.num_episodes), 1)),
        "--record-every-n",
        str(max(int(args.record_every_n), 1)),
        "--record-episode-timeout-s",
        str(max(float(args.episode_timeout_s), 1.0)),
        "--camera-width",
        str(max(int(args.camera_width), 1)),
        "--camera-height",
        str(max(int(args.camera_height), 1)),
        "--auto-grasp",
        "--auto-grasp-block",
        args.block,
        "--randomize-blue-xy",
        str(max(float(args.randomize_blue_xy), 0.0)),
        "--random-seed",
        str(int(args.random_seed)),
        *(["--headless"] if args.no_render else []),
        *passthrough,
    ]
    runpy.run_path(str(sim_script), run_name="__main__")


if __name__ == "__main__":
    main()
