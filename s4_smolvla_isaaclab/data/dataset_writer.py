"""Small HDF5 writer for staged S4 demonstrations.

This module intentionally has no IsaacLab dependency. The simulator side should
collect numpy arrays and call this writer at episode boundaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from . import hdf5_schema as schema


def _create_nested_dataset(group: h5py.Group, path: str, data: np.ndarray, **dataset_kwargs: Any) -> None:
    parent = group
    parts = path.split("/")
    for part in parts[:-1]:
        parent = parent.require_group(part)
    parent.create_dataset(parts[-1], data=data, **dataset_kwargs)


def _image_dataset_kwargs(data: np.ndarray) -> dict[str, Any]:
    if data.ndim != 4:
        return {}
    return {
        "compression": "gzip",
        "compression_opts": 4,
        "shuffle": True,
        "chunks": (1, *data.shape[1:]),
    }


@dataclass
class EpisodeBuffer:
    metadata: dict[str, Any] = field(default_factory=dict)
    actions: list[np.ndarray] = field(default_factory=list)
    full_joint_pos: list[np.ndarray] = field(default_factory=list)
    active_joint_pos: list[np.ndarray] = field(default_factory=list)
    chest_front_rgb: list[np.ndarray] = field(default_factory=list)
    task_descriptions: list[str] = field(default_factory=list)
    left_wrist_rgb: list[np.ndarray] = field(default_factory=list)
    right_wrist_rgb: list[np.ndarray] = field(default_factory=list)
    left_eef_pose: list[np.ndarray] = field(default_factory=list)
    right_eef_pose: list[np.ndarray] = field(default_factory=list)
    red_block_pose: list[np.ndarray] = field(default_factory=list)
    blue_block_pose: list[np.ndarray] = field(default_factory=list)
    plate_pose: list[np.ndarray] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.actions)

    def validate(self) -> None:
        lengths: dict[str, int] = {
            "actions": len(self.actions),
            "full_joint_pos": len(self.full_joint_pos),
            "chest_front_rgb": len(self.chest_front_rgb),
        }
        optional_sequences = {
            "active_joint_pos": self.active_joint_pos,
            "task_descriptions": self.task_descriptions,
            "left_wrist_rgb": self.left_wrist_rgb,
            "right_wrist_rgb": self.right_wrist_rgb,
            "left_eef_pose": self.left_eef_pose,
            "right_eef_pose": self.right_eef_pose,
            "red_block_pose": self.red_block_pose,
            "blue_block_pose": self.blue_block_pose,
            "plate_pose": self.plate_pose,
        }
        lengths.update({name: len(values) for name, values in optional_sequences.items() if values})
        if len(set(lengths.values())) != 1:
            raise ValueError(f"Episode arrays have mismatched lengths: {lengths}")
        if not self.actions:
            raise ValueError("EpisodeBuffer is empty")


class Hdf5DemoWriter:
    def __init__(self, path: Path, env_args: dict[str, Any]):
        self.path = Path(path)
        self.env_args = env_args
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = h5py.File(self.path, "w")
        self._data = self._file.create_group("data")
        self._data.attrs["env_args"] = json.dumps(env_args, ensure_ascii=False)
        self._episode_index = 0

    def write_episode(self, episode: EpisodeBuffer) -> str:
        episode.validate()
        name = f"demo_{self._episode_index}"
        group = self._data.create_group(name)
        if episode.metadata:
            group.attrs["episode_metadata"] = json.dumps(episode.metadata, ensure_ascii=False)
        _create_nested_dataset(group, schema.PROCESSED_ACTIONS, np.asarray(episode.actions, dtype=np.float32))
        _create_nested_dataset(group, schema.FULL_JOINT_POS, np.asarray(episode.full_joint_pos, dtype=np.float32))
        if episode.active_joint_pos:
            _create_nested_dataset(group, schema.ACTIVE_JOINT_POS, np.asarray(episode.active_joint_pos, dtype=np.float32))
        if episode.task_descriptions:
            string_dtype = h5py.string_dtype(encoding="utf-8")
            _create_nested_dataset(
                group,
                schema.TASK_DESCRIPTION,
                np.asarray(episode.task_descriptions, dtype=object),
                dtype=string_dtype,
            )
        rgb = np.asarray(episode.chest_front_rgb, dtype=np.uint8)
        _create_nested_dataset(group, schema.CHEST_FRONT_RGB, rgb, **_image_dataset_kwargs(rgb))
        if episode.left_wrist_rgb:
            left_rgb = np.asarray(episode.left_wrist_rgb, dtype=np.uint8)
            _create_nested_dataset(group, schema.LEFT_WRIST_RGB, left_rgb, **_image_dataset_kwargs(left_rgb))
        if episode.right_wrist_rgb:
            right_rgb = np.asarray(episode.right_wrist_rgb, dtype=np.uint8)
            _create_nested_dataset(group, schema.RIGHT_WRIST_RGB, right_rgb, **_image_dataset_kwargs(right_rgb))
        if episode.left_eef_pose:
            _create_nested_dataset(group, schema.LEFT_EEF_POSE, np.asarray(episode.left_eef_pose, dtype=np.float32))
        if episode.right_eef_pose:
            _create_nested_dataset(group, schema.RIGHT_EEF_POSE, np.asarray(episode.right_eef_pose, dtype=np.float32))
        if episode.red_block_pose:
            _create_nested_dataset(group, schema.RED_BLOCK_POSE, np.asarray(episode.red_block_pose, dtype=np.float32))
        if episode.blue_block_pose:
            _create_nested_dataset(group, schema.BLUE_BLOCK_POSE, np.asarray(episode.blue_block_pose, dtype=np.float32))
        if episode.plate_pose:
            _create_nested_dataset(group, schema.PLATE_POSE, np.asarray(episode.plate_pose, dtype=np.float32))
        self._episode_index += 1
        self._file.flush()
        return name

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "Hdf5DemoWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
