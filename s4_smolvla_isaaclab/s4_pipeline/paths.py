"""Project paths and local environment discovery.

Committed configuration uses environment-variable placeholders.  This module
is the only place that supplies workstation defaults and reads ``.env``.
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_DIR = Path(os.environ.get("S4_PROJECT_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
WORKSPACE_DIR = PROJECT_DIR.parent
CONFIG_DIR = PROJECT_DIR / "configs"
LOCAL_DIR = PROJECT_DIR / ".local"


def _load_dotenv(path: Path = PROJECT_DIR / ".env") -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv()

PATH_DEFAULTS = {
    "S4_PROJECT_ROOT": str(PROJECT_DIR),
    "ISAACLAB_ROOT": str(Path.home() / "IsaacLab"),
    "ISAAC_ASSET_ROOT": str(Path.home() / "isaacsim_assets/Assets/Isaac/5.1"),
    "S4_SCENE_ASSET_ROOT": str(PROJECT_DIR / "local_assets" / "isaac" / "5.1"),
    "LEROBOT_ROOT": str(WORKSPACE_DIR / "lerobot"),
    "SMOLVLA_MODEL_ROOT": str(PROJECT_DIR / "models"),
    "S4_DATA_ROOT": str(PROJECT_DIR / "datasets"),
    "S4_OUTPUT_ROOT": str(PROJECT_DIR / "outputs"),
    "S4_CACHE_ROOT": str(PROJECT_DIR / ".cache"),
    "S4_ISAACLAB_ENV": "env_isaaclab",
    "S4_SMOLVLA_ENV": "smolvla",
}
for _key, _value in PATH_DEFAULTS.items():
    os.environ.setdefault(_key, _value)


def active_task_id() -> str:
    env_task = os.environ.get("S4_TASK")
    if env_task:
        return env_task.strip()
    local_task = LOCAL_DIR / "active_task"
    if local_task.is_file():
        value = local_task.read_text(encoding="utf-8").strip()
        if value:
            return value
    return (CONFIG_DIR / "active_task.default").read_text(encoding="utf-8").strip()


def task_dataset_config_path(task_id: str | None = None) -> Path:
    return CONFIG_DIR / "tasks" / f"{task_id or active_task_id()}.dataset.json"


def task_training_config_path(task_id: str | None = None) -> Path:
    return CONFIG_DIR / "tasks" / f"{task_id or active_task_id()}.smolvla.yaml"


DATASET_CONFIG_PATH = task_dataset_config_path()
SMOLVLA_CONFIG_PATH = task_training_config_path()
ASSETS_DIR = PROJECT_DIR / "assets"
LOCAL_SCENE_ASSETS_DIR = Path(os.environ["S4_SCENE_ASSET_ROOT"]).expanduser()
DATASETS_DIR = Path(os.environ["S4_DATA_ROOT"]).expanduser()
MODELS_DIR = Path(os.environ["SMOLVLA_MODEL_ROOT"]).expanduser()
OUTPUTS_DIR = Path(os.environ["S4_OUTPUT_ROOT"]).expanduser()
REFERENCE_LEROBOT_DIR = Path(os.environ["LEROBOT_ROOT"]).expanduser()
