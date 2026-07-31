#!/bin/bash
# S4 Isaac Lab 快捷运行脚本
# 用法:
#   bash run.sh sim
#   bash run.sh inspect-config
#   bash run.sh record-hdf5
#   bash run.sh record-parallel
#   bash run.sh convert-lerobot
#   bash run.sh train-smolvla
#   bash run.sh pipeline
#   bash run.sh preview-smolvla
#   bash run.sh visualize-smolvla
#   bash run.sh control reach-block --block blue
#   python scripts/set_joint_command.py right_elbow_joint=0.3

set -euo pipefail
cd "$(dirname "$0")"

ISAACLAB="${HOME}/IsaacLab/isaaclab.sh"
ISAACLAB_PY="/home/zfy/miniconda3/envs/env_isaaclab/bin"
ISAACLAB_CMEEL="/home/zfy/miniconda3/envs/env_isaaclab/lib/python3.11/site-packages/cmeel.prefix"

use_isaaclab_env() {
    export CONDA_PREFIX=""
    export PATH="${ISAACLAB_PY}:$PATH"
    export PYTHONPATH="${ISAACLAB_CMEEL}/lib/python3.11/site-packages:${PYTHONPATH:-}"
    export LD_LIBRARY_PATH="${ISAACLAB_CMEEL}/lib:${LD_LIBRARY_PATH:-}"
    export PYTHONUNBUFFERED=1
}

split_record_args() {
    ISAAC_APP_ARGS=()
    SCRIPT_ARGS=()
    OUTPUT_PATH=""
    RECORD_EPISODES=""
    AUTO_GRASP_BLOCK="blue"
    EPISODE_TIMEOUT=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --output)
                OUTPUT_PATH="$2"
                shift 2
                ;;
            --num-episodes)
                RECORD_EPISODES="$2"
                shift 2
                ;;
            --block)
                AUTO_GRASP_BLOCK="$2"
                shift 2
                ;;
            --episode-timeout-s)
                EPISODE_TIMEOUT="$2"
                shift 2
                ;;
            --no-render)
                ISAAC_APP_ARGS+=(--headless)
                shift
                ;;
            --render)
                shift
                ;;
            *)
                SCRIPT_ARGS+=("$1")
                shift
                ;;
        esac
    done
    if [[ -z "$OUTPUT_PATH" ]]; then
        OUTPUT_PATH="$(python3 - <<'PY'
from s4_pipeline.config import load_project_config
print(load_project_config().dataset.staging_root / "s4_right_blue_cylinder_plate_scripted.hdf5")
PY
)"
    fi
    if [[ -z "$RECORD_EPISODES" ]]; then
        RECORD_EPISODES="1"
    fi
    if [[ -z "$EPISODE_TIMEOUT" ]]; then
        EPISODE_TIMEOUT="120"
    fi
    SCRIPT_ARGS=(
        --record-output "$OUTPUT_PATH"
        --record-episodes "$RECORD_EPISODES"
        --record-episode-timeout-s "$EPISODE_TIMEOUT"
        --auto-grasp
        --auto-grasp-block "$AUTO_GRASP_BLOCK"
        "${SCRIPT_ARGS[@]}"
    )
}

case "${1:-sim}" in
    inspect-config)
        shift
        python3 scripts/00_inspect_project.py "$@"
        ;;
    sim)
        shift
        use_isaaclab_env
        $ISAACLAB -p scripts/03_record_physics_dataset.py --enable_cameras --print-layout "$@"
        ;;
    record-hdf5)
        shift
        use_isaaclab_env
        split_record_args "$@"
        $ISAACLAB -p scripts/03_record_physics_dataset.py --enable_cameras "${ISAAC_APP_ARGS[@]}" "${SCRIPT_ARGS[@]}"
        ;;
    record-parallel)
        shift
        python3 scripts/11_record_parallel_hdf5.py "$@"
        ;;
    clean-generated)
        shift
        python3 scripts/10_clean_generated.py "$@"
        ;;
    convert-lerobot)
        shift
        python3 scripts/05_convert_hdf5_to_lerobot.py "$@"
        ;;
    train-smolvla)
        shift
        bash scripts/train_smolvla_local.sh "$@"
        ;;
    pipeline)
        shift
        bash scripts/12_collect_convert_train.sh "$@"
        ;;
    preview-smolvla)
        shift
        python3 scripts/07_preview_smolvla_policy.py "$@"
        ;;
    visualize-smolvla)
        shift
        python3 scripts/08_visualize_smolvla_policy.py "$@"
        ;;
    eval-smolvla)
        shift
        use_isaaclab_env
        $ISAACLAB -p scripts/06_eval_smolvla_in_isaaclab.py --enable_cameras "$@"
        ;;
    joint-debug)
        shift
        use_isaaclab_env
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
        use_isaaclab_env
        $ISAACLAB -p "$script" --headless "$@"
        ;;
    *)
        echo "用法: bash run.sh {inspect-config|sim|record-hdf5|record-parallel|clean-generated|convert-lerobot|train-smolvla|pipeline|preview-smolvla|visualize-smolvla|eval-smolvla|control|reach-block|joint-debug|headless <script>}"
        exit 1
        ;;
esac
