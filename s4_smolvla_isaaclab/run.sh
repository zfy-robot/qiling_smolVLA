#!/bin/bash
# S4 Isaac Lab 快捷运行脚本
# 用法:
#   bash run.sh sim
#   bash run.sh inspect-config
#   bash run.sh list-tasks
#   bash run.sh activate-task right_blue_cylinder_plate
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
ISAAC_LOCAL_ASSET_ROOT="/home/zfy/isaacsim_assets/Assets/Isaac/5.1"
ISAAC_ASSET_ROOT_KIT_ARGS="--/persistent/isaac/asset_root/default=${ISAAC_LOCAL_ASSET_ROOT} --/persistent/isaac/asset_root/cloud=${ISAAC_LOCAL_ASSET_ROOT} --/persistent/isaac/asset_root/nvidia=${ISAAC_LOCAL_ASSET_ROOT} --/persistent/isaac/asset_root/timeout=1"
ISAAC_KIT_BROWSER_ARGS="--/exts/omni.kit.browser.asset/folders/0=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Environments --/exts/omni.kit.browser.asset/folders/1=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Props --/exts/omni.kit.browser.asset/folders/2=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Robots --/exts/omni.kit.browser.asset/folders/3=file:${ISAAC_LOCAL_ASSET_ROOT}/NVIDIA/Assets/ArchVis/Commercial --/exts/omni.kit.browser.asset/folders/4=file:${ISAAC_LOCAL_ASSET_ROOT}/NVIDIA/Assets/ArchVis/Industrial --/exts/omni.kit.browser.asset/folders/5=file:${ISAAC_LOCAL_ASSET_ROOT}/NVIDIA/Assets/ArchVis/Residential --/exts/omni.kit.browser.asset/folders/6=file:${ISAAC_LOCAL_ASSET_ROOT}/NVIDIA/Assets/DigitalTwin/Assets/Warehouse/Equipment --/exts/omni.kit.browser.asset/folders/7=file:${ISAAC_LOCAL_ASSET_ROOT}/NVIDIA/Assets/DigitalTwin/Assets/Warehouse/Storage --/exts/omni.kit.browser.asset/data/timeout=1 --/exts/omni.kit.browser.asset/visible_after_startup=false"
ISAAC_SIM_BROWSER_ARGS="--/exts/isaacsim.asset.browser/folders/0=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Environments --/exts/isaacsim.asset.browser/folders/1=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Props --/exts/isaacsim.asset.browser/folders/2=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Robots --/exts/isaacsim.asset.browser/folders/3= --/exts/isaacsim.asset.browser/folders/4= --/exts/isaacsim.asset.browser/folders/5= --/exts/isaacsim.asset.browser/folders/6= --/exts/isaacsim.asset.browser/folders/7= --/exts/isaacsim.asset.browser/data/timeout=1 --/exts/isaacsim.asset.browser/data/hide_file_without_thumbnails=false --/exts/isaacsim.asset.browser/visible_after_startup=false"
ISAAC_GUI_CONTENT_BROWSER_ARGS="--/exts/isaacsim.gui.content_browser/folders/0=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Environments --/exts/isaacsim.gui.content_browser/folders/1=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Props --/exts/isaacsim.gui.content_browser/folders/2=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Robots --/exts/isaacsim.gui.content_browser/folders/3= --/exts/isaacsim.gui.content_browser/folders/4= --/exts/isaacsim.gui.content_browser/folders/5= --/exts/isaacsim.gui.content_browser/folders/6= --/exts/isaacsim.gui.content_browser/folders/7= --/exts/isaacsim.gui.content_browser/timeout=1"
ISAAC_LEGACY_BROWSER_ARGS="--/exts/omni.isaac.asset_browser/folder/0=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Robots --/exts/omni.isaac.asset_browser/folder/1=file:${ISAAC_LOCAL_ASSET_ROOT}/Isaac/Environments --/exts/omni.isaac.asset_browser/data/timeout=1 --/exts/omni.isaac.asset_browser/visible_after_startup=false"
ISAAC_LOCAL_KIT_ARGS="${ISAAC_ASSET_ROOT_KIT_ARGS} ${ISAAC_KIT_BROWSER_ARGS} ${ISAAC_SIM_BROWSER_ARGS} ${ISAAC_GUI_CONTENT_BROWSER_ARGS} ${ISAAC_LEGACY_BROWSER_ARGS}"

use_isaaclab_env() {
    export CONDA_PREFIX=""
    export PATH="${ISAACLAB_PY}:$PATH"
    export PYTHONPATH="${ISAACLAB_CMEEL}/lib/python3.11/site-packages:${PYTHONPATH:-}"
    export LD_LIBRARY_PATH="${ISAACLAB_CMEEL}/lib:${LD_LIBRARY_PATH:-}"
    export PYTHONUNBUFFERED=1
    export ISAAC_LOCAL_ASSET_ROOT
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
        --kit_args "$ISAAC_LOCAL_KIT_ARGS"
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
        python3 scripts/inspect_project.py "$@"
        ;;
    list-tasks)
        shift
        python3 scripts/inspect_tasks.py "$@"
        ;;
    activate-task)
        shift
        python3 scripts/activate_task.py "$@"
        ;;
    sim)
        shift
        use_isaaclab_env
        $ISAACLAB -p scripts/record_dataset.py --enable_cameras --kit_args "$ISAAC_LOCAL_KIT_ARGS" --print-layout --continuous "$@"
        ;;
    record-hdf5)
        shift
        use_isaaclab_env
        split_record_args "$@"
        $ISAACLAB -p scripts/record_dataset.py --enable_cameras "${ISAAC_APP_ARGS[@]}" "${SCRIPT_ARGS[@]}"
        ;;
    record-parallel)
        shift
        python3 scripts/record_parallel.py "$@"
        ;;
    clean-generated)
        shift
        python3 scripts/clean_generated.py "$@"
        ;;
    convert-lerobot)
        shift
        python3 scripts/convert_lerobot.py "$@"
        ;;
    train-smolvla)
        shift
        bash scripts/train_smolvla_local.sh "$@"
        ;;
    pipeline)
        shift
        bash scripts/pipeline_collect_convert_train.sh "$@"
        ;;
    preview-smolvla)
        shift
        python3 scripts/preview_policy.py "$@"
        ;;
    visualize-smolvla)
        shift
        python3 scripts/visualize_policy.py "$@"
        ;;
    eval-smolvla)
        shift
        use_isaaclab_env
        $ISAACLAB -p scripts/eval_policy.py --enable_cameras --kit_args "$ISAAC_LOCAL_KIT_ARGS" "$@"
        ;;
    joint-debug)
        shift
        use_isaaclab_env
        $ISAACLAB -p scripts/joint_debug.py --enable_cameras "$@"
        ;;
    control)
        shift
        python3 scripts/control_arm.py "$@"
        ;;
    reach-block)
        shift
        python3 scripts/control_arm.py reach-block "$@"
        ;;
    headless)
        script="$2"; shift 2
        use_isaaclab_env
        $ISAACLAB -p "$script" --headless --kit_args "$ISAAC_LOCAL_KIT_ARGS" "$@"
        ;;
    *)
        echo "用法: bash run.sh {inspect-config|list-tasks|activate-task|sim|record-hdf5|record-parallel|clean-generated|convert-lerobot|train-smolvla|pipeline|preview-smolvla|visualize-smolvla|eval-smolvla|control|reach-block|joint-debug|headless <script>}"
        exit 1
        ;;
esac
