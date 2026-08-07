from pathlib import Path

import h5py
import numpy as np

from data.dataset_writer import EpisodeBuffer, Hdf5DemoWriter


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
