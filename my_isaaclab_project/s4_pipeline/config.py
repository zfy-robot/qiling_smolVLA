"""Typed config loading for the S4 bimanual pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import DATASET_CONFIG_PATH


@dataclass(frozen=True)
class DatasetSpec:
    repo_id: str
    staging_root: Path
    root: Path
    lerobot_root: Path
    fps: int
    task: str


@dataclass(frozen=True)
class SceneSpec:
    scene_usd: Path
    table_usd: Path | None
    table_top_z: float


@dataclass(frozen=True)
class FeatureSpec:
    state_dim: int
    active_state_dim: int
    action_dim: int
    camera_key: str
    camera_shape: tuple[int, int, int]


@dataclass(frozen=True)
class TrainingSpec:
    env_name: str
    policy_type: str
    pretrained_policy: str
    output_dir: Path
    target_episodes_first_pass: int
    target_episodes_training_pass: int


@dataclass(frozen=True)
class ProjectConfig:
    dataset: DatasetSpec
    scene: SceneSpec
    features: FeatureSpec
    training: TrainingSpec
    raw: dict[str, Any]


def _required(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise KeyError(f"Missing required config key: {key}")
    return mapping[key]


def load_project_config(path: Path = DATASET_CONFIG_PATH) -> ProjectConfig:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    dataset_raw = _required(raw, "dataset")
    scene_raw = _required(raw, "scene")
    features_raw = _required(raw, "features")
    training_raw = _required(raw, "training")

    state_shape = _required(features_raw["observation.state"], "shape")
    active_state_shape = features_raw.get("observation.active_state", {}).get("shape", [26])
    action_shape = _required(features_raw["action"], "shape")
    camera_shape = _required(features_raw["observation.images.front"], "shape")

    dataset = DatasetSpec(
        repo_id=str(_required(dataset_raw, "repo_id")),
        staging_root=Path(_required(dataset_raw, "staging_root")),
        root=Path(_required(dataset_raw, "root")),
        lerobot_root=Path(dataset_raw.get("lerobot_root", Path(dataset_raw["root"]).parent / "lerobot_data")),
        fps=int(_required(dataset_raw, "fps")),
        task=str(_required(dataset_raw, "task")),
    )
    table_usd_raw = scene_raw.get("table_usd")
    scene = SceneSpec(
        scene_usd=Path(_required(scene_raw, "scene_usd")),
        table_usd=None if table_usd_raw in (None, "", "none") else Path(table_usd_raw),
        table_top_z=float(_required(scene_raw, "table_top_z")),
    )
    features = FeatureSpec(
        state_dim=int(state_shape[0]),
        active_state_dim=int(active_state_shape[0]),
        action_dim=int(action_shape[0]),
        camera_key="observation.images.front",
        camera_shape=tuple(int(x) for x in camera_shape),
    )
    training = TrainingSpec(
        env_name=str(_required(training_raw, "env_name")),
        policy_type=str(_required(training_raw, "policy_type")),
        pretrained_policy=str(_required(training_raw, "pretrained_policy")),
        output_dir=Path(_required(training_raw, "output_dir")),
        target_episodes_first_pass=int(_required(training_raw, "target_episodes_first_pass")),
        target_episodes_training_pass=int(_required(training_raw, "target_episodes_training_pass")),
    )
    return ProjectConfig(dataset=dataset, scene=scene, features=features, training=training, raw=raw)
