#!/usr/bin/env python3
"""Launch multiple independent IsaacLab recording workers."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.config import load_project_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def split_counts(total: int, workers: int) -> list[int]:
    total = max(int(total), 1)
    workers = max(int(workers), 1)
    base = total // workers
    rem = total % workers
    return [base + (1 if i < rem else 0) for i in range(workers) if base + (1 if i < rem else 0) > 0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Record HDF5 demos with multiple IsaacLab worker processes.")
    parser.add_argument("--num-episodes", type=int, default=100)
    parser.add_argument("--workers", type=int, default=2, help="Number of IsaacLab processes. Start with 2-4 before trying 10.")
    parser.add_argument("--block", choices=["red", "blue"], default="blue")
    parser.add_argument("--no-render", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--randomize-blue-xy", type=float, default=0.03)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--record-every-n", type=int, default=6)
    parser.add_argument("--episode-timeout-s", type=float, default=120.0)
    parser.add_argument("--reset-settle-s", type=float, default=2.0)
    parser.add_argument("--camera-width", type=int, default=680)
    parser.add_argument("--camera-height", type=int, default=480)
    parser.add_argument("--output-dir", type=Path, default=None)
    args, passthrough = parser.parse_known_args()

    cfg = load_project_config()
    output_dir = args.output_dir or cfg.dataset.staging_root
    output_dir.mkdir(parents=True, exist_ok=True)

    counts = split_counts(args.num_episodes, args.workers)
    processes: list[tuple[int, subprocess.Popen]] = []
    for worker_id, count in enumerate(counts):
        output = output_dir / f"s4_right_blue_cylinder_plate_scripted_worker{worker_id:02d}.hdf5"
        cmd = [
            "bash",
            "run.sh",
            "record-hdf5",
            "--output",
            str(output),
            "--num-episodes",
            str(count),
            "--block",
            args.block,
            "--record-every-n",
            str(max(int(args.record_every_n), 1)),
            "--episode-timeout-s",
            str(max(float(args.episode_timeout_s), 1.0)),
            "--reset-settle-s",
            str(max(float(args.reset_settle_s), 0.0)),
            "--randomize-blue-xy",
            str(max(float(args.randomize_blue_xy), 0.0)),
            "--random-seed",
            str(int(args.random_seed) + worker_id),
            "--camera-width",
            str(max(int(args.camera_width), 1)),
            "--camera-height",
            str(max(int(args.camera_height), 1)),
            *(["--no-render"] if args.no_render else []),
            *passthrough,
        ]
        print(f"[PARALLEL] worker={worker_id} episodes={count} output={output}")
        processes.append((worker_id, subprocess.Popen(cmd, cwd=PROJECT_ROOT)))

    failed: list[int] = []
    for worker_id, proc in processes:
        ret = proc.wait()
        if ret != 0:
            failed.append(worker_id)
            print(f"[PARALLEL] worker={worker_id} failed exit={ret}")
        else:
            print(f"[PARALLEL] worker={worker_id} done")

    if failed:
        raise SystemExit(f"Recording workers failed: {failed}")
    print(f"[PARALLEL] complete: {sum(counts)} episodes across {len(counts)} files under {output_dir}")


if __name__ == "__main__":
    main()
