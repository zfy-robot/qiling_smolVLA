#!/usr/bin/env bash
set -euo pipefail

policy_python="${S4_SMOLVLA_PYTHON:-/opt/conda/envs/smolvla/bin/python}"
dataset_root="${S4_DATA_ROOT:-/artifacts/datasets}/lerobot_data/s4_drawer_insert_close_v4_12phase_serial_acquire"
vlm_root="${SMOLVLA_MODEL_ROOT:-/artifacts/models}/HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
base_policy_root="${SMOLVLA_MODEL_ROOT:-/artifacts/models}/lerobot/smolvla_base"

fail() {
    echo "[FAIL] $*" >&2
    exit 1
}

require_file() {
    [[ -f "$1" ]] || fail "missing required file: $1"
    echo "[OK] $1"
}

require_file "$dataset_root/meta/info.json"
require_file "$dataset_root/meta/s4_contract.json"
require_file "$dataset_root/data/chunk-000/file-000.parquet"
require_file "$vlm_root/model.safetensors"
require_file "$vlm_root/tokenizer.json"
require_file "$base_policy_root/config.json"
require_file "$base_policy_root/model.safetensors"
require_file "$base_policy_root/policy_preprocessor.json"
require_file "$base_policy_root/policy_postprocessor.json"

for camera_key in \
    observation.images.chest_front_rgb \
    observation.images.left_wrist_rgb \
    observation.images.right_wrist_rgb; do
    if ! find "$dataset_root/videos/$camera_key" -type f -name '*.mp4' -print -quit | grep -q .; then
        fail "no MP4 files found for $camera_key"
    fi
    echo "[OK] dataset videos: $camera_key"
done

[[ -x "$policy_python" ]] || fail "policy Python is not executable: $policy_python"
command -v lerobot-train >/dev/null || fail "lerobot-train is not on PATH"
command -v accelerate >/dev/null || fail "accelerate is not on PATH"
[[ "$(command -v lerobot-train)" == /opt/conda/envs/smolvla/bin/* ]] \
    || fail "lerobot-train resolved outside the smolvla environment: $(command -v lerobot-train)"
[[ "$(command -v accelerate)" == /opt/conda/envs/smolvla/bin/* ]] \
    || fail "accelerate resolved outside the smolvla environment: $(command -v accelerate)"
echo "[OK] policy CLI: $(command -v lerobot-train)"
echo "[OK] accelerate CLI: $(command -v accelerate)"

"$policy_python" -m pip check

S4_VERIFY_VLM_ROOT="$vlm_root" \
S4_VERIFY_BASE_POLICY_ROOT="$base_policy_root" \
"$policy_python" - <<'PY'
import importlib.metadata as metadata
import os
from pathlib import Path

import accelerate
import av
import datasets
import lerobot
import pyarrow
import torch
import transformers
from lerobot.configs.policies import PreTrainedConfig
from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig  # noqa: F401
from transformers import AutoProcessor

if not torch.cuda.is_available():
    raise RuntimeError("CUDA is unavailable in the policy container")
if torch.version.cuda != "12.8":
    raise RuntimeError(f"expected PyTorch CUDA 12.8, got {torch.version.cuda}")

device_name = torch.cuda.get_device_name(0)
probe = torch.ones(8, device="cuda")
if float(probe.sum().item()) != 8.0:
    raise RuntimeError("CUDA tensor probe failed")

vlm_root = Path(os.environ["S4_VERIFY_VLM_ROOT"])
base_policy_root = Path(os.environ["S4_VERIFY_BASE_POLICY_ROOT"])
processor = AutoProcessor.from_pretrained(vlm_root, local_files_only=True)
policy_config = PreTrainedConfig.from_pretrained(base_policy_root, local_files_only=True)
if policy_config.type != "smolvla":
    raise RuntimeError(f"expected smolvla policy config, got {policy_config.type!r}")

print(
    "[OK] policy imports:",
    f"python torch={torch.__version__}",
    f"lerobot={metadata.version('lerobot')}",
    f"transformers={transformers.__version__}",
    f"accelerate={accelerate.__version__}",
    f"datasets={datasets.__version__}",
    f"pyarrow={pyarrow.__version__}",
    f"av={av.__version__}",
)
print(f"[OK] CUDA policy runtime: {device_name} cuda={torch.version.cuda}")
print(f"[OK] local VLM processor: {type(processor).__name__}")
print("[OK] local SmolVLA base config")
PY

"$policy_python" scripts/dataset_check.py "$dataset_root"
echo "[OK] policy runtime verification passed"
