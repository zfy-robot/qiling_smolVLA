#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "project_commit=$(git -C "$ROOT" rev-parse HEAD)"
echo "project_dirty=$(test -n "$(git -C "$ROOT" status --short)" && echo true || echo false)"
echo "lerobot_commit=$(git -C "${LEROBOT_ROOT:-$ROOT/../lerobot}" rev-parse HEAD)"
echo "isaaclab_commit=$(git -C "${ISAACLAB_ROOT:-$HOME/IsaacLab}" rev-parse HEAD)"
conda run -n "${S4_ISAACLAB_ENV:-env_isaaclab}" python -c \
  'import sys,torch,importlib.metadata as m; print("isaaclab_python",sys.version.split()[0]); print("torch",torch.__version__,"cuda",torch.version.cuda); print("isaacsim",m.version("isaacsim")); print("isaaclab",m.version("isaaclab"))'
conda run -n "${S4_SMOLVLA_ENV:-smolvla}" python -c \
  'import sys,torch,lerobot,av,transformers; print("smolvla_python",sys.version.split()[0]); print("torch",torch.__version__,"cuda",torch.version.cuda); print("lerobot",lerobot.__version__); print("pyav",av.__version__); print("transformers",transformers.__version__)'
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
