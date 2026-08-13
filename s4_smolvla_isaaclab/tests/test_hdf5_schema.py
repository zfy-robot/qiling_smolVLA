from pathlib import Path

import h5py
import numpy as np
import pytest

from data.dataset_writer import EpisodeBuffer, Hdf5DemoWriter
from data.lerobot_conversion import validate_scene_contracts
from s4_pipeline.drawer_distractors import asset_contract


def test_hdf5_writer_contract(tmp_path: Path):
    episode = EpisodeBuffer(
        actions=[np.zeros(26, dtype=np.float32)],
        full_joint_pos=[np.zeros(48, dtype=np.float32)],
        active_joint_pos=[np.zeros(26, dtype=np.float32)],
        task_descriptions=["test phase"],
        chest_front_rgb=[np.zeros((8, 8, 3), dtype=np.uint8)],
        left_wrist_rgb=[np.zeros((8, 8, 3), dtype=np.uint8)],
        right_wrist_rgb=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    path = tmp_path / "fixture.hdf5"
    with Hdf5DemoWriter(path, {"record_fps": 20}) as writer:
        writer.write_episode(episode)
    with h5py.File(path, "r") as stream:
        assert stream["data/demo_0/processed_actions"].shape == (1, 26)
        assert stream["data/demo_0/obs/chest_front_rgb"].shape == (1, 8, 8, 3)


def test_hdf5_writer_rejects_partial_camera_sequence(tmp_path: Path):
    episode = EpisodeBuffer(
        actions=[np.zeros(26, dtype=np.float32), np.zeros(26, dtype=np.float32)],
        full_joint_pos=[np.zeros(48, dtype=np.float32), np.zeros(48, dtype=np.float32)],
        chest_front_rgb=[np.zeros((8, 8, 3), dtype=np.uint8)] * 2,
        left_wrist_rgb=[np.zeros((8, 8, 3), dtype=np.uint8)],
    )
    with Hdf5DemoWriter(tmp_path / "bad.hdf5", {"record_fps": 20}) as writer:
        with pytest.raises(ValueError, match="mismatched lengths"):
            writer.write_episode(episode)


def test_scene_contract_rejects_mixed_distractor_assets(tmp_path: Path):
    current = tmp_path / "current.hdf5"
    legacy = tmp_path / "legacy.hdf5"
    with Hdf5DemoWriter(
        current,
        {"distractor_cans_enabled": True, "distractor_assets": asset_contract()},
    ):
        pass
    with Hdf5DemoWriter(
        legacy,
        {"distractor_cans_enabled": True, "distractor_assets": []},
    ):
        pass
    with pytest.raises(ValueError, match="different distractor scene contracts"):
        validate_scene_contracts([current, legacy])
