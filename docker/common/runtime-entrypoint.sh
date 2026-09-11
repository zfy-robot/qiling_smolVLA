#!/usr/bin/env bash
set -euo pipefail

export S4_PROJECT_ROOT="${S4_PROJECT_ROOT:-/workspace/smolVLA/s4_smolvla_isaaclab}"
export ISAACLAB_ROOT="${ISAACLAB_ROOT:-/workspace/smolVLA/IsaacLab}"
export LEROBOT_ROOT="${LEROBOT_ROOT:-/workspace/smolVLA/lerobot}"
export S4_ARTIFACT_ROOT="${S4_ARTIFACT_ROOT:-/artifacts}"
export SMOLVLA_MODEL_ROOT="${SMOLVLA_MODEL_ROOT:-$S4_ARTIFACT_ROOT/models}"
export S4_DATA_ROOT="${S4_DATA_ROOT:-$S4_ARTIFACT_ROOT/datasets}"
export S4_PROJECT_ASSET_ROOT="${S4_PROJECT_ASSET_ROOT:-$S4_ARTIFACT_ROOT/assets}"
export S4_ROBOT_ASSET_ROOT="${S4_ROBOT_ASSET_ROOT:-$S4_PROJECT_ASSET_ROOT/my_robot}"
export S4_PROJECT_SCENE_ASSET_ROOT="${S4_PROJECT_SCENE_ASSET_ROOT:-$S4_PROJECT_ASSET_ROOT/scenes}"
export S4_OUTPUT_ROOT="${S4_OUTPUT_ROOT:-/workspace/outputs}"
export S4_CACHE_ROOT="${S4_CACHE_ROOT:-/workspace/cache}"
export S4_SCENE_ASSET_ROOT="${S4_SCENE_ASSET_ROOT:-/workspace/isaac-assets/5.1}"
export ISAAC_ASSET_ROOT="${ISAAC_ASSET_ROOT:-$S4_SCENE_ASSET_ROOT}"
runtime_env_bin=""
if [[ -n "${S4_SMOLVLA_PYTHON:-}" && -x "${S4_SMOLVLA_PYTHON}" ]]; then
    runtime_env_bin="$(dirname "${S4_SMOLVLA_PYTHON}")"
fi
if [[ -n "${runtime_env_bin}" ]]; then
    export PATH="${runtime_env_bin}:/opt/conda/bin:${PATH}"
    export CONDA_PREFIX="${runtime_env_bin%/bin}"
else
    export PATH="/opt/conda/bin:${PATH}"
fi
export PYTHONUNBUFFERED=1

if [[ ! -d "$S4_PROJECT_ROOT" ]]; then
    echo "[FAIL] project source is not mounted at $S4_PROJECT_ROOT" >&2
    exit 1
fi
mkdir -p "$S4_OUTPUT_ROOT" "$S4_CACHE_ROOT" "${XDG_RUNTIME_DIR:-/tmp/s4-xdg-runtime}"
cd "$S4_PROJECT_ROOT"
exec "$@"
