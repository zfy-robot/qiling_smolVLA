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
    default=120.0,
    help="Discard and retry an episode if scripted collection exceeds this wall-clock timeout.",
)
parser.add_argument("--success-check", action=argparse.BooleanOptionalAction, default=True)
parser.add_argument("--success-xy-tolerance", type=float, default=None)
parser.add_argument("--success-z-min-above-plate", type=float, default=-0.02)
parser.add_argument("--success-z-max-above-plate", type=float, default=0.20)
parser.add_argument("--reset-settle-s", type=float, default=2.0, help="Simulated seconds to settle after scene load/reset before starting a task.")
parser.add_argument("--camera-width", type=int, default=680)
parser.add_argument("--camera-height", type=int, default=480)
parser.add_argument("--camera-eye", type=float, nargs=3, default=[0.18, -0.62, 1.42])
parser.add_argument("--camera-target", type=float, nargs=3, default=[0.52, -0.12, 0.98])
parser.add_argument("--camera-rpy-deg", type=float, nargs=3, default=[-11.0, -26.0, -95.0])
parser.add_argument("--camera-convention", choices=["opengl", "ros", "world"], default="opengl")
parser.add_argument(
    "--camera-look-at",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Use --camera-eye -> --camera-target look-at for /World/DebugFrontCamera. Pass --no-camera-look-at to use --camera-rpy-deg.",
)
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
        *(["--success-check"] if args.success_check else ["--no-success-check"]),
        *(
            []
            if args.success_xy_tolerance is None
            else ["--success-xy-tolerance", str(float(args.success_xy_tolerance))]
        ),
        "--success-z-min-above-plate",
        str(float(args.success_z_min_above_plate)),
        "--success-z-max-above-plate",
        str(float(args.success_z_max_above_plate)),
        "--reset-settle-s",
        str(max(float(args.reset_settle_s), 0.0)),
        "--camera-width",
        str(max(int(args.camera_width), 1)),
        "--camera-height",
        str(max(int(args.camera_height), 1)),
        "--camera-eye",
        *(str(float(x)) for x in args.camera_eye),
        "--camera-target",
        *(str(float(x)) for x in args.camera_target),
        "--camera-convention",
        args.camera_convention,
        *(["--camera-look-at"] if args.camera_look_at else ["--camera-rpy-deg", *(str(float(x)) for x in args.camera_rpy_deg)]),
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
