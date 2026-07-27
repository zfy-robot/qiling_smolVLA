"""Local HDF5 to LeRobotDataset conversion utilities.

The implementation mirrors the relevant BenchHub flow but stays in this
project. It imports LeRobot lazily so IsaacLab-side smoke checks can run
without the training environment installed.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from . import hdf5_schema as schema


VIDEO_INFO = {
    "video.fps": 30.0,
    "video.codec": "h264",
    "video.pix_fmt": "yuv420p",
    "video.is_depth_map": False,
    "has_audio": False,
}


def discover_hdf5_files(root_path: Path) -> list[Path]:
    root_path = Path(root_path)
    if root_path.is_file() and root_path.suffix == ".hdf5":
        return [root_path]
    if root_path.is_dir():
        return sorted(root_path.glob("*.hdf5"))
    raise FileNotFoundError(f"HDF5 root does not exist: {root_path}")


def inspect_first_demo(hdf5_path: Path, camera_path: str) -> tuple[int, int, tuple[int, ...]]:
    with h5py.File(hdf5_path, "r") as f:
        demo_names = sorted(f["data"].keys(), key=lambda x: int(x.split("_")[-1]))
        for demo_name in demo_names:
            demo = f["data"][demo_name]
            if schema.PROCESSED_ACTIONS in demo and schema.FULL_JOINT_POS in demo and camera_path in demo:
                action_dim = int(np.asarray(demo[schema.PROCESSED_ACTIONS]).shape[1])
                state_dim = int(np.asarray(demo[schema.FULL_JOINT_POS]).shape[1])
                camera_shape = tuple(np.asarray(demo[camera_path][0]).shape)
                return state_dim, action_dim, camera_shape
    raise ValueError(f"No valid demo found in {hdf5_path}")


def build_lerobot_features(camera_paths: list[str], state_dim: int, action_dim: int, camera_shape: tuple[int, ...]) -> dict:
    features = {
        "observation.state": {"dtype": "float32", "shape": (state_dim,), "names": None},
        "action": {"dtype": "float32", "shape": (action_dim,), "names": None},
        "episode_index": {"dtype": "int64", "shape": (1,), "names": None},
        "frame_index": {"dtype": "int64", "shape": (1,), "names": None},
        "index": {"dtype": "int64", "shape": (1,), "names": None},
        "task_index": {"dtype": "int64", "shape": (1,), "names": None},
    }
    for camera_path in camera_paths:
        camera_name = camera_path.split("/")[-1]
        features[f"observation.images.{camera_name}"] = {
            "dtype": "video",
            "shape": camera_shape,
            "names": ["height", "width", "channel"],
            "video_info": VIDEO_INFO,
        }
    return features


def convert_hdf5_to_lerobot(
    root_path: Path,
    output_root: Path,
    repo_id: str,
    task_description: str,
    robot_type: str,
    camera_paths: list[str] | None = None,
    fps: int = 30,
) -> Path:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    camera_paths = camera_paths or [schema.CHEST_FRONT_RGB]
    hdf5_files = discover_hdf5_files(root_path)
    if not hdf5_files:
        raise FileNotFoundError(f"No .hdf5 files found under {root_path}")

    state_dim, action_dim, camera_shape = inspect_first_demo(hdf5_files[0], camera_paths[0])
    features = build_lerobot_features(camera_paths, state_dim, action_dim, camera_shape)
    dataset_root = Path(output_root) / repo_id

    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        root=str(dataset_root),
        fps=fps,
        robot_type=robot_type,
        features=features,
        vcodec="h264",
    )

    for hdf5_path in hdf5_files:
        with h5py.File(hdf5_path, "r") as f:
            demo_names = sorted(f["data"].keys(), key=lambda x: int(x.split("_")[-1]))
            for demo_name in demo_names:
                demo = f["data"][demo_name]
                if schema.PROCESSED_ACTIONS not in demo:
                    continue
                actions = np.asarray(demo[schema.PROCESSED_ACTIONS])
                states = np.asarray(demo[schema.FULL_JOINT_POS])
                cameras = {path: np.asarray(demo[path]) for path in camera_paths}
                frame_count = min([len(actions), len(states), *(len(v) for v in cameras.values())])
                for i in range(frame_count):
                    frame = {
                        "observation.state": states[i].astype(np.float32),
                        "action": actions[i].astype(np.float32),
                        "task": task_description,
                    }
                    for camera_path, values in cameras.items():
                        camera_name = camera_path.split("/")[-1]
                        frame[f"observation.images.{camera_name}"] = values[i]
                    dataset.add_frame(frame)
                dataset.save_episode()
    return dataset_root

