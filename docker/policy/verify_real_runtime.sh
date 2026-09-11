#!/usr/bin/env bash
set -euo pipefail

project_root="${S4_PROJECT_ROOT:-/workspace/smolVLA/s4_smolvla_isaaclab}"
dataset_root="${S4_DATA_ROOT:-/artifacts/datasets}/lerobot_data/s4_real_drawer_right_v1"
checkpoint="${S4_REAL_POLICY_CHECKPOINT:-/artifacts/policies/real/drawer_right_v1/300000/pretrained_model}"

required=(
  "${dataset_root}/meta/info.json"
  "${dataset_root}/meta/s4_contract.json"
  "${dataset_root}/meta/s4_source_index.parquet"
  "${dataset_root}/data/chunk-000/file-000.parquet"
  "${checkpoint}/config.json"
  "${checkpoint}/model.safetensors"
  "${checkpoint}/policy_preprocessor.json"
  "${checkpoint}/policy_postprocessor.json"
)
for path in "${required[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[FAIL] missing required real-policy artifact: ${path}" >&2
    exit 1
  fi
  echo "[OK] ${path}"
done

cd "${project_root}"
python -m real_vla_stack.cli dataset-check
python -m real_vla_stack.cli checkpoint-check --checkpoint "${checkpoint}"
echo "[OK] real dataset and 300K checkpoint runtime verification passed"
