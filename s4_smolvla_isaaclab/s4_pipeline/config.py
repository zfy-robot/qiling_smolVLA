"""Typed project and training configuration loading."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from .paths import task_dataset_config_path, task_training_config_path


@dataclass(frozen=True)
class DatasetSpec:
    task_id: str
    schema_version: str
    repo_id: str
    staging_root: Path
    root: Path
    lerobot_root: Path
    fps: int
    control_fps: int
    action_semantics: str
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
    camera_keys: tuple[str, ...]
    camera_shapes: dict[str, tuple[int, int, int]]

    @property
    def camera_key(self) -> str:
        return self.camera_keys[0]

    @property
    def camera_shape(self) -> tuple[int, int, int]:
        return self.camera_shapes[self.camera_key]


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
    source: Path


def _required(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise KeyError(f"Missing required config key: {key}")
    return mapping[key]


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return Template(value).safe_substitute(os.environ)
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


def load_project_config(path: Path | None = None) -> ProjectConfig:
    source = Path(path) if path is not None else task_dataset_config_path()
    raw = _expand(json.loads(source.read_text(encoding="utf-8")))
    dataset_raw = _required(raw, "dataset")
    scene_raw = _required(raw, "scene")
    features_raw = _required(raw, "features")
    training_raw = _required(raw, "training")

    camera_keys = tuple(key for key in features_raw if key.startswith("observation.images."))
    if not camera_keys:
        raise KeyError("Missing required config key: observation.images.*")
    camera_shapes = {
        key: tuple(int(x) for x in _required(features_raw[key], "shape")) for key in camera_keys
    }
    dataset = DatasetSpec(
        task_id=str(raw.get("task_id", dataset_raw.get("task_id", "drawer_insert_close"))),
        schema_version=str(_required(raw, "schema_version")),
        repo_id=str(_required(dataset_raw, "repo_id")),
        staging_root=Path(_required(dataset_raw, "staging_root")).expanduser(),
        root=Path(_required(dataset_raw, "root")).expanduser(),
        lerobot_root=Path(_required(dataset_raw, "lerobot_root")).expanduser(),
        fps=int(_required(dataset_raw, "fps")),
        control_fps=int(_required(dataset_raw, "control_fps")),
        action_semantics=str(_required(dataset_raw, "action_semantics")),
        task=str(_required(dataset_raw, "task")),
    )
    table_usd_raw = scene_raw.get("table_usd")
    scene = SceneSpec(
        scene_usd=Path(_required(scene_raw, "scene_usd")).expanduser(),
        table_usd=None if table_usd_raw in (None, "", "none") else Path(table_usd_raw).expanduser(),
        table_top_z=float(_required(scene_raw, "table_top_z")),
    )
    state_shape = _required(features_raw["observation.state"], "shape")
    active_shape = features_raw.get("observation.active_state", {}).get("shape", state_shape)
    action_shape = _required(features_raw["action"], "shape")
    features = FeatureSpec(
        state_dim=int(state_shape[0]),
        active_state_dim=int(active_shape[0]),
        action_dim=int(action_shape[0]),
        camera_keys=camera_keys,
        camera_shapes=camera_shapes,
    )
    training = TrainingSpec(
        env_name=str(_required(training_raw, "env_name")),
        policy_type=str(_required(training_raw, "policy_type")),
        pretrained_policy=str(_required(training_raw, "pretrained_policy")),
        output_dir=Path(_required(training_raw, "output_dir")).expanduser(),
        target_episodes_first_pass=int(_required(training_raw, "target_episodes_first_pass")),
        target_episodes_training_pass=int(_required(training_raw, "target_episodes_training_pass")),
    )
    return ProjectConfig(dataset, scene, features, training, raw, source)


def load_training_config(path: Path | None = None) -> dict[str, Any]:
    import yaml

    source = Path(path) if path is not None else task_training_config_path()
    return _expand(yaml.safe_load(source.read_text(encoding="utf-8")))
