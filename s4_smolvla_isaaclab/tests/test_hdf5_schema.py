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
        drawer_task_object_pose=[np.asarray([0.52, -0.13, 1.16, 1.0, 0.0, 0.0, 0.0], dtype=np.float32)],
    )
    path = tmp_path / "fixture.hdf5"
    with Hdf5DemoWriter(path, {"record_fps": 20}) as writer:
        writer.write_episode(episode)
    with h5py.File(path, "r") as stream:
        assert stream["data/demo_0/processed_actions"].shape == (1, 26)
        assert stream["data/demo_0/obs/chest_front_rgb"].shape == (1, 8, 8, 3)
        assert stream["data/demo_0/states/rigid_object/drawer_task_object/root_pose"].shape == (1, 7)


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


def test_hdf5_writer_resume_appends_and_restores_collection_state(tmp_path: Path):
    path = tmp_path / "resume.hdf5"
    env_args = {"task": "drawer", "record_every_n": 6}
    episode = EpisodeBuffer(
        actions=[np.zeros(26, dtype=np.float32)],
        full_joint_pos=[np.zeros(48, dtype=np.float32)],
        chest_front_rgb=[np.zeros((4, 4, 3), dtype=np.uint8)],
    )
    with Hdf5DemoWriter(path, env_args) as writer:
        assert writer.write_episode(episode) == "demo_0"
        writer.write_collection_state({"completed_episodes": 1, "cursor": 7})

    with Hdf5DemoWriter(path, env_args, resume=True) as writer:
        assert writer.episode_count == 1
        assert writer.read_collection_state() == {"completed_episodes": 1, "cursor": 7}
        assert writer.write_episode(
            episode,
            collection_state={"completed_episodes": 2, "cursor": 8},
        ) == "demo_1"
        assert writer.read_collection_state() == {"completed_episodes": 2, "cursor": 8}

    with h5py.File(path, "r") as stream:
        assert sorted(stream["data"].keys()) == ["demo_0", "demo_1"]


def test_hdf5_writer_resume_rejects_changed_contract(tmp_path: Path):
    path = tmp_path / "contract.hdf5"
    with Hdf5DemoWriter(path, {"task": "drawer", "record_every_n": 6}):
        pass
    with pytest.raises(ValueError, match="collection contract changed"):
        Hdf5DemoWriter(path, {"task": "drawer", "record_every_n": 3}, resume=True)


def test_hdf5_writer_never_silently_overwrites(tmp_path: Path):
    path = tmp_path / "keep.hdf5"
    with Hdf5DemoWriter(path, {"task": "drawer"}):
        pass
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        Hdf5DemoWriter(path, {"task": "drawer"}, overwrite=False)
    with pytest.raises(FileNotFoundError, match="Cannot resume missing"):
        Hdf5DemoWriter(tmp_path / "typo.hdf5", {"task": "drawer"}, resume=True)


def test_resume_accepts_new_retry_policy_but_not_sampling_region_change(tmp_path: Path):
    path = tmp_path / "live_old_process.hdf5"
    old = {"task": "drawer", "randomization": {"can_xy": {"x_range": [-0.05, 0.05]}}}
    with Hdf5DemoWriter(path, old):
        pass
    retry_policy = {
        "task": "drawer",
        "randomization": {"can_xy": {"x_range": [-0.05, 0.05], "max_points_per_cell": 3}},
    }
    with Hdf5DemoWriter(path, retry_policy, resume=True):
        pass

    changed_region = {
        "task": "drawer",
        "randomization": {"can_xy": {"x_range": [-0.04, 0.04], "max_points_per_cell": 3}},
    }
    with pytest.raises(ValueError, match="collection contract changed"):
        Hdf5DemoWriter(path, changed_region, resume=True)
