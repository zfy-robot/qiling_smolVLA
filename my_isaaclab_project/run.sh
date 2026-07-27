#!/bin/bash
# S4 Isaac Lab 快捷运行脚本
# 用法:
#   bash run.sh sim
#   bash run.sh control reach-block --block blue
#   python scripts/set_joint_command.py right_elbow_joint=0.3

set -euo pipefail
cd "$(dirname "$0")"

# 确保使用 env_isaaclab 环境的 Python
export CONDA_PREFIX=""
export PATH="/home/zfy/miniconda3/envs/env_isaaclab/bin:$PATH"

ISAACLAB="${HOME}/IsaacLab/isaaclab.sh"

case "${1:-sim}" in
    sim)
        shift
        $ISAACLAB -p scripts/03_record_physics_dataset.py --enable_cameras "$@"
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
        echo "用法: bash run.sh {sim|control|reach-block|joint-debug|headless <script>}"
        exit 1
        ;;
esac
