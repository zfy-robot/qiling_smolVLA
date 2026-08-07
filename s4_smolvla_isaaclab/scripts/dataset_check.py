#!/usr/bin/env python3
"""Validate HDF5 or LeRobotDataset data against the active task contract."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.config import load_project_config


def _fail(message: str) -> None:
    raise ValueError(message)


def _check_hdf5(path: Path, cfg) -> None:
    import h5py
    import numpy as np
    from data.hdf5_schema import CHEST_FRONT_RGB, LEFT_WRIST_RGB, PROCESSED_ACTIONS, RIGHT_WRIST_RGB

    files = [path] if path.is_file() else sorted(path.rglob("*.hdf5"))
    if not files:
        _fail(f"No HDF5 files under {path}")
    episodes = frames = 0
    for file in files:
        with h5py.File(file, "r") as stream:
            for name, group in stream["data"].items():
                action = group[PROCESSED_ACTIONS]
                if action.ndim != 2 or action.shape[1] != cfg.features.action_dim:
                    _fail(f"{file}:{name} action shape={action.shape}")
                count = action.shape[0]
                for key, feature in zip(
                    (CHEST_FRONT_RGB, LEFT_WRIST_RGB, RIGHT_WRIST_RGB), cfg.features.camera_keys, strict=True
                ):
                    image = group[key]
                    expected = (count, *cfg.features.camera_shapes[feature])
                    if image.shape != expected:
                        _fail(f"{file}:{name}:{key} shape={image.shape}, expected={expected}")
                if not np.isfinite(action[:]).all():
                    _fail(f"{file}:{name} contains NaN/Inf actions")
                episodes += 1
                frames += count
    print(f"[OK] HDF5 files={len(files)} episodes={episodes} frames={frames} action=26D cameras=3 schema={cfg.dataset.schema_version}")


def _check_lerobot(path: Path, cfg, checkpoint: Path | None) -> None:
    import av
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    info = json.loads((path / "meta/info.json").read_text(encoding="utf-8"))
    if cfg.dataset.action_semantics != "absolute_joint_target":
        _fail(f"unsupported action semantics: {cfg.dataset.action_semantics}")
    features = info["features"]
    if int(info["fps"]) != cfg.dataset.fps:
        _fail(f"fps={info['fps']}, expected={cfg.dataset.fps}")
    for key in ("observation.state", "action"):
        if features[key]["shape"] != [26]:
            _fail(f"{key} shape={features[key]['shape']}, expected=[26]")
    for key in cfg.features.camera_keys:
        if features[key]["shape"] != list(cfg.features.camera_shapes[key]):
            _fail(f"{key} shape={features[key]['shape']}")
    parquet_files = sorted((path / "data").rglob("*.parquet"))
    if not parquet_files:
        _fail("No frame parquet files")
    tables = [pq.read_table(p, columns=["timestamp", "episode_index", "frame_index", "task_index", "observation.state", "action"]) for p in parquet_files]
    table = pa.concat_tables(tables)
    for key in ("observation.state", "action"):
        values = np.asarray(table.column(key).to_pylist(), dtype=np.float32)
        if values.ndim != 2 or values.shape[1] != 26 or not np.isfinite(values).all():
            _fail(f"{key} invalid shape or NaN/Inf: {values.shape}")
    timestamps = table.column("timestamp").to_pylist()
    episodes = table.column("episode_index").to_pylist()
    frames = table.column("frame_index").to_pylist()
    previous: dict[int, tuple[float, int]] = {}
    for timestamp, episode, frame in zip(timestamps, episodes, frames, strict=True):
        ep = int(episode)
        if ep in previous and (float(timestamp) <= previous[ep][0] or int(frame) != previous[ep][1] + 1):
            _fail(f"non-monotonic episode={ep} frame={frame} timestamp={timestamp}")
        previous[ep] = (float(timestamp), int(frame))
    video_files = []
    for key in cfg.features.camera_keys:
        candidates = sorted((path / "videos" / key).rglob("*.mp4"))
        if not candidates:
            _fail(f"No videos for {key}")
        video_files.extend(candidates)
        with av.open(str(candidates[0])) as container:
            frame = next(container.decode(video=0))
            if (frame.height, frame.width, 3) != cfg.features.camera_shapes[key]:
                _fail(f"decoded {key} shape={(frame.height, frame.width, 3)}")
    task_rows = pq.read_table(path / "meta/tasks.parquet")
    if task_rows.num_rows == 0:
        _fail("tasks.parquet is empty")
    if checkpoint:
        model = checkpoint / "pretrained_model" if (checkpoint / "pretrained_model").is_dir() else checkpoint
        ckpt = json.loads((model / "config.json").read_text(encoding="utf-8"))
        inputs = ckpt["input_features"]
        expected_inputs = {"observation.state", *cfg.features.camera_keys}
        if set(inputs) != expected_inputs or ckpt["output_features"]["action"]["shape"] != [26]:
            _fail(f"checkpoint feature contract mismatch: {model}")
    print(f"[OK] LeRobotDataset episodes={len(previous)} frames={table.num_rows} fps={info['fps']} action/state=26D schema={cfg.dataset.schema_version}")
    print(f"[OK] cameras=3 shape=480x680x3 decoded_files={len(video_files)} tasks={task_rows.num_rows}")
    if checkpoint:
        print(f"[OK] checkpoint compatible: {checkpoint}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate active-task HDF5 or LeRobotDataset data.")
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--hdf5", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()
    cfg = load_project_config()
    default = cfg.dataset.staging_root if args.hdf5 else cfg.dataset.lerobot_root / cfg.dataset.repo_id.split("/")[-1]
    path = (args.path or default).expanduser().resolve()
    if not path.exists():
        _fail(f"Path does not exist: {path}")
    _check_hdf5(path, cfg) if args.hdf5 else _check_lerobot(path, cfg, args.checkpoint)


if __name__ == "__main__":
    main()
