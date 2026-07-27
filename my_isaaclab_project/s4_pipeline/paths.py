"""Central paths for the local S4 SmolVLA project."""

from __future__ import annotations

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
CONFIG_DIR = PROJECT_DIR / "configs"
DATASET_CONFIG_PATH = CONFIG_DIR / "s4_bimanual_dataset.json"
SMOLVLA_CONFIG_PATH = CONFIG_DIR / "smolvla_s4_bimanual.yaml"

DATASETS_DIR = WORKSPACE_DIR / "datasets"
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"

REFERENCE_BENCHHUB_DIR = WORKSPACE_DIR / "qi-studio-benchhub"
REFERENCE_LEROBOT_DIR = WORKSPACE_DIR / "lerobot"

