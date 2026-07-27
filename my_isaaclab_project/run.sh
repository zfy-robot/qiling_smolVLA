#!/bin/bash
# S4 Isaac Lab 快捷运行脚本
# 用法:
#   bash run.sh sim
#   bash run.sh inspect-config
#   bash run.sh record-hdf5
#   bash run.sh convert-lerobot
#   bash run.sh train-smolvla
#   bash run.sh control reach-block --block blue
#   python scripts/set_joint_command.py right_elbow_joint=0.3

set -euo pipefail
cd "$(dirname "$0")"

# 确保使用 env_isaaclab 环境的 Python
export CONDA_PREFIX=""
export PATH="/home/zfy/miniconda3/envs/env_isaaclab/bin:$PATH"
export PYTHONPATH="/home/zfy/miniconda3/envs/env_isaaclab/lib/python3.11/site-packages/cmeel.prefix/lib/python3.11/site-packages:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="/home/zfy/miniconda3/envs/env_isaaclab/lib/python3.11/site-packages/cmeel.prefix/lib:${LD_LIBRARY_PATH:-}"

ISAACLAB="${HOME}/IsaacLab/isaaclab.sh"

case "${1:-sim}" in
    inspect-config)
        shift
        python3 scripts/00_inspect_project.py "$@"
        ;;
    sim)
        shift
        $ISAACLAB -p scripts/03_record_physics_dataset.py --enable_cameras --print-layout --show-tcp-frames "$@"
        ;;
    record-hdf5)
        shift
        $ISAACLAB -p scripts/04_record_bimanual_hdf5.py --enable_cameras "$@"
        ;;
    convert-lerobot)
        shift
        python3 scripts/05_convert_hdf5_to_lerobot.py "$@"
        ;;
    train-smolvla)
        shift
        bash scripts/train_smolvla_local.sh "$@"
        ;;
    eval-smolvla)
        shift
        $ISAACLAB -p scripts/06_eval_smolvla_in_isaaclab.py --enable_cameras "$@"
        ;;
    joint-debug)
        shift
        $ISAACLAB -p scripts/03_joint_debug.py --enable_cameras "$@"
        ;;
    control)
        shift
        python scripts/control_arm.py "$@"
        ;;
    reach-block)
        shift
        python scripts/control_arm.py reach-block "$@"
        ;;
    headless)
        script="$2"; shift 2
        $ISAACLAB -p "$script" --headless "$@"
        ;;
    *)
        echo "用法: bash run.sh {inspect-config|sim|record-hdf5|convert-lerobot|train-smolvla|eval-smolvla|control|reach-block|joint-debug|headless <script>}"
        exit 1
        ;;
esac
