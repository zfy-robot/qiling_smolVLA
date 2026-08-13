#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

ORIGINAL_PATH="$PATH"
SMOLVLA_PREFIX="${S4_SMOLVLA_PREFIX:-${SMOLVLA_PREFIX:-$HOME/miniconda3/envs/smolvla}}"
SMOLVLA_BIN="${SMOLVLA_BIN:-${SMOLVLA_PREFIX}/bin}"

use_smolvla_env() {
    export CONDA_PREFIX="$SMOLVLA_PREFIX"
    export PATH="${SMOLVLA_BIN}:$ORIGINAL_PATH"
}

NUM_EPISODES=100
WORKERS=1
BLOCK="blue"
NO_RENDER=true
RANDOMIZE_BLUE_XY=0.03
RANDOM_SEED=42
RECORD_EVERY_N=6
EPISODE_TIMEOUT_S=300
RESET_SETTLE_S=2.0
SUCCESS_CHECK=true
SUCCESS_XY_TOLERANCE=""
SUCCESS_Z_MIN_ABOVE_PLATE=-0.02
SUCCESS_Z_MAX_ABOVE_PLATE=0.20
CAMERA_WIDTH=680
CAMERA_HEIGHT=480
TRAIN_CONFIG="$(python3 -c 'from s4_pipeline.paths import SMOLVLA_CONFIG_PATH; print(SMOLVLA_CONFIG_PATH)')"
TRAIN_STEPS=""
BATCH_SIZE=""
SAVE_FREQ=""
CLEAN_FIRST=false
OVERWRITE_DATASET=false
OVERWRITE_OUTPUT=false
SKIP_RECORD=false
SKIP_CONVERT=false
SKIP_TRAIN=false
DRY_RUN=false
OUTPUT_DIR=""
HDF5_ROOT_PATH=""
HDF5_ROOT_PATH_PROVIDED=false

usage() {
    cat <<'EOF'
Usage:
  bash run.sh pipeline [options]

Main options:
  --num-episodes N          Number of scripted episodes to collect. Default: 100
  --workers N               IsaacSim recording workers. Default: 1
  --block blue|red          Object to script. Default: blue
  --no-render               Headless collection while still recording camera frames. Default
  --render                  Show rendering during collection.
  --randomize-blue-xy M     Per-episode blue cylinder x/y randomization range. Default: 0.03
  --random-seed N           Random seed. Default: 42
  --record-every-n N        Record every N sim steps. Default: 6
  --episode-timeout-s S     Discard/retry stuck episode after S wall seconds. Default: 300
  --reset-settle-s S        Sim seconds to settle after scene load/reset before starting task. Default: 2.0
  --success-check           Only keep episodes where the cylinder finishes inside the plate. Default
  --no-success-check        Disable final success filtering.
  --success-xy-tolerance M  Max final cylinder-to-plate XY distance. Default: plate radius - cylinder radius.
  --success-z-min M         Min final cylinder center height relative to plate center. Default: -0.02
  --success-z-max M         Max final cylinder center height relative to plate center. Default: 0.20

Training options:
  --steps N                 Override training steps.
  --batch-size N            Override training batch size.
  --save-freq N             Override checkpoint save frequency.
  --config PATH             Training config. Default: active task config

Overwrite/cleanup:
  --clean-first             Delete generated staging/LeRobot/train/eval outputs before running.
  --overwrite-dataset       Rebuild existing LeRobotDataset output.
  --overwrite-output        Delete existing training output before training.

Advanced:
  --output-dir PATH         HDF5 output directory. Default: timestamped subdir under configured staging root.
  --hdf5-root-path PATH     Existing HDF5 file/dir for conversion; implies --skip-record.
  --skip-record             Skip HDF5 collection.
  --skip-convert            Skip LeRobot conversion.
  --skip-train              Skip training.
  --dry-run                 Print the planned stages and environment, then exit.
  -h, --help                Show this help.

Example:
  bash run.sh pipeline --num-episodes 100 --workers 4 --no-render \
    --overwrite-dataset --overwrite-output --steps 50000 --batch-size 4 --save-freq 5000
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --num-episodes)
            NUM_EPISODES="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --block)
            BLOCK="$2"
            shift 2
            ;;
        --no-render)
            NO_RENDER=true
            shift
            ;;
        --render)
            NO_RENDER=false
            shift
            ;;
        --randomize-blue-xy)
            RANDOMIZE_BLUE_XY="$2"
            shift 2
            ;;
        --random-seed)
            RANDOM_SEED="$2"
            shift 2
            ;;
        --record-every-n)
            RECORD_EVERY_N="$2"
            shift 2
            ;;
        --episode-timeout-s)
            EPISODE_TIMEOUT_S="$2"
            shift 2
            ;;
        --reset-settle-s)
            RESET_SETTLE_S="$2"
            shift 2
            ;;
        --success-check)
            SUCCESS_CHECK=true
            shift
            ;;
        --no-success-check)
            SUCCESS_CHECK=false
            shift
            ;;
        --success-xy-tolerance)
            SUCCESS_XY_TOLERANCE="$2"
            shift 2
            ;;
        --success-z-min)
            SUCCESS_Z_MIN_ABOVE_PLATE="$2"
            shift 2
            ;;
        --success-z-max)
            SUCCESS_Z_MAX_ABOVE_PLATE="$2"
            shift 2
            ;;
        --camera-width)
            CAMERA_WIDTH="$2"
            shift 2
            ;;
        --camera-height)
            CAMERA_HEIGHT="$2"
            shift 2
            ;;
        --steps)
            TRAIN_STEPS="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --save-freq)
            SAVE_FREQ="$2"
            shift 2
            ;;
        --config)
            TRAIN_CONFIG="$2"
            shift 2
            ;;
        --clean-first)
            CLEAN_FIRST=true
            shift
            ;;
        --overwrite-dataset)
            OVERWRITE_DATASET=true
            shift
            ;;
        --overwrite-output)
            OVERWRITE_OUTPUT=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --hdf5-root-path)
            HDF5_ROOT_PATH="$2"
            HDF5_ROOT_PATH_PROVIDED=true
            SKIP_RECORD=true
            shift 2
            ;;
        --skip-record)
            SKIP_RECORD=true
            shift
            ;;
        --skip-convert)
            SKIP_CONVERT=true
            shift
            ;;
        --skip-train)
            SKIP_TRAIN=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown pipeline option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$BLOCK" != "blue" && "$BLOCK" != "red" ]]; then
    echo "--block must be blue or red" >&2
    exit 2
fi

if [[ "$SKIP_RECORD" == true && "$SKIP_CONVERT" != true && "$HDF5_ROOT_PATH_PROVIDED" != true ]]; then
    echo "--skip-record with conversion requires --hdf5-root-path <existing hdf5 file or directory>" >&2
    exit 2
fi

use_smolvla_env
ACTIVE_TASK_ID="$(python3 - <<'PY'
from s4_pipeline.config import load_project_config
print(load_project_config().dataset.task_id)
PY
)"
if [[ -z "$OUTPUT_DIR" ]]; then
    STAGING_ROOT="$(python3 - <<'PY'
from s4_pipeline.config import load_project_config
print(load_project_config().dataset.staging_root)
PY
)"
    RUN_ID="$(date +%Y%m%d_%H%M%S)"
    OUTPUT_DIR="${STAGING_ROOT}/pipeline_${RUN_ID}"
fi

if [[ -z "$HDF5_ROOT_PATH" ]]; then
    HDF5_ROOT_PATH="$OUTPUT_DIR"
fi

echo "========================================"
echo "  S4 collect -> convert -> train pipeline"
echo "  Episodes:     $NUM_EPISODES"
echo "  Workers:      $WORKERS"
echo "  Block:        $BLOCK"
echo "  No render:    $NO_RENDER"
echo "  HDF5 root:    $HDF5_ROOT_PATH"
echo "  Train config: $TRAIN_CONFIG"
echo "  Timeout:      ${EPISODE_TIMEOUT_S}s per episode attempt"
echo "  Reset settle: ${RESET_SETTLE_S}s"
echo "  SmolVLA py:   $(command -v python3)"
echo "  SmolVLA train:$(command -v lerobot-train || true)"
echo "========================================"
echo "[PIPELINE] env split:"
echo "[PIPELINE]   record stages call run.sh record, which switches child process to env_isaaclab via IsaacLab/isaaclab.sh"
echo "[PIPELINE]   convert/train stages use SMOLVLA_PREFIX=$SMOLVLA_PREFIX"

if [[ "$DRY_RUN" == true ]]; then
    echo "[PIPELINE] dry run only; no collection, conversion, or training started."
    exit 0
fi

if [[ "$CLEAN_FIRST" == true ]]; then
    use_smolvla_env
    echo "[PIPELINE] cleaning generated project outputs first"
    bash run.sh clean-generated --yes
fi

if [[ "$SKIP_RECORD" != true ]]; then
    mkdir -p "$OUTPUT_DIR"
    if (( WORKERS > 1 )); then
        echo "[PIPELINE] recording HDF5 with $WORKERS direct record workers"
        BASE_COUNT=$((NUM_EPISODES / WORKERS))
        REMAINDER=$((NUM_EPISODES % WORKERS))
        PIDS=()
        WORKER_IDS=()
        for ((WORKER_ID=0; WORKER_ID<WORKERS; WORKER_ID++)); do
            COUNT=$BASE_COUNT
            if (( WORKER_ID < REMAINDER )); then
                COUNT=$((COUNT + 1))
            fi
            if (( COUNT <= 0 )); then
                continue
            fi
            WORKER_OUTPUT="${OUTPUT_DIR}/${ACTIVE_TASK_ID}_scripted_worker$(printf '%02d' "$WORKER_ID").hdf5"
            RECORD_CMD=(
                bash run.sh record
                --output "$WORKER_OUTPUT"
                --num-episodes "$COUNT"
                --block "$BLOCK"
                --randomize-blue-xy "$RANDOMIZE_BLUE_XY"
                --random-seed "$((RANDOM_SEED + WORKER_ID))"
                --record-every-n "$RECORD_EVERY_N"
                --episode-timeout-s "$EPISODE_TIMEOUT_S"
                --reset-settle-s "$RESET_SETTLE_S"
                --success-z-min-above-plate "$SUCCESS_Z_MIN_ABOVE_PLATE"
                --success-z-max-above-plate "$SUCCESS_Z_MAX_ABOVE_PLATE"
                --camera-width "$CAMERA_WIDTH"
                --camera-height "$CAMERA_HEIGHT"
            )
            if [[ "$SUCCESS_CHECK" == true ]]; then
                RECORD_CMD+=(--success-check)
            else
                RECORD_CMD+=(--no-success-check)
            fi
            if [[ -n "$SUCCESS_XY_TOLERANCE" ]]; then
                RECORD_CMD+=(--success-xy-tolerance "$SUCCESS_XY_TOLERANCE")
            fi
            if [[ "$NO_RENDER" == true ]]; then
                RECORD_CMD+=(--no-render)
            fi
            printf '[PIPELINE] worker=%d episodes=%d command:' "$WORKER_ID" "$COUNT"
            printf ' %q' "${RECORD_CMD[@]}"
            printf '\n'
            "${RECORD_CMD[@]}" &
            PIDS+=("$!")
            WORKER_IDS+=("$WORKER_ID")
        done
        FAILED_WORKERS=()
        for IDX in "${!PIDS[@]}"; do
            PID="${PIDS[$IDX]}"
            WORKER_ID="${WORKER_IDS[$IDX]}"
            if wait "$PID"; then
                echo "[PIPELINE] worker=$WORKER_ID done"
            else
                STATUS="$?"
                echo "[PIPELINE] worker=$WORKER_ID failed exit=$STATUS" >&2
                FAILED_WORKERS+=("$WORKER_ID")
            fi
        done
        if (( ${#FAILED_WORKERS[@]} > 0 )); then
            echo "[PIPELINE] recording workers failed: ${FAILED_WORKERS[*]}" >&2
            exit 1
        fi
    else
        HDF5_FILE="${OUTPUT_DIR}/${ACTIVE_TASK_ID}_scripted.hdf5"
        HDF5_ROOT_PATH="$HDF5_FILE"
        echo "[PIPELINE] recording HDF5 to $HDF5_FILE"
        RECORD_CMD=(
            bash run.sh record
            --output "$HDF5_FILE"
            --num-episodes "$NUM_EPISODES"
            --block "$BLOCK"
            --randomize-blue-xy "$RANDOMIZE_BLUE_XY"
            --random-seed "$RANDOM_SEED"
            --record-every-n "$RECORD_EVERY_N"
            --episode-timeout-s "$EPISODE_TIMEOUT_S"
            --reset-settle-s "$RESET_SETTLE_S"
            --success-z-min-above-plate "$SUCCESS_Z_MIN_ABOVE_PLATE"
            --success-z-max-above-plate "$SUCCESS_Z_MAX_ABOVE_PLATE"
            --camera-width "$CAMERA_WIDTH"
            --camera-height "$CAMERA_HEIGHT"
        )
        if [[ "$SUCCESS_CHECK" == true ]]; then
            RECORD_CMD+=(--success-check)
        else
            RECORD_CMD+=(--no-success-check)
        fi
        if [[ -n "$SUCCESS_XY_TOLERANCE" ]]; then
            RECORD_CMD+=(--success-xy-tolerance "$SUCCESS_XY_TOLERANCE")
        fi
        if [[ "$NO_RENDER" == true ]]; then
            RECORD_CMD+=(--no-render)
        fi
        "${RECORD_CMD[@]}"
    fi
    if [[ -d "$HDF5_ROOT_PATH" ]]; then
        HDF5_COUNT="$(find "$HDF5_ROOT_PATH" -maxdepth 1 -type f -name '*.hdf5' | wc -l)"
        if [[ "$HDF5_COUNT" -le 0 ]]; then
            echo "[PIPELINE] no HDF5 files found after recording under: $HDF5_ROOT_PATH" >&2
            exit 1
        fi
        echo "[PIPELINE] recording produced $HDF5_COUNT HDF5 file(s) under $HDF5_ROOT_PATH"
    elif [[ -f "$HDF5_ROOT_PATH" ]]; then
        echo "[PIPELINE] recording produced HDF5 file: $HDF5_ROOT_PATH"
    else
        echo "[PIPELINE] expected HDF5 output does not exist: $HDF5_ROOT_PATH" >&2
        exit 1
    fi
fi

if [[ "$SKIP_CONVERT" != true ]]; then
    use_smolvla_env
    CONVERT_ARGS=()
    if [[ "$OVERWRITE_DATASET" == true ]]; then
        CONVERT_ARGS+=(--overwrite)
    fi
    echo "[PIPELINE] converting HDF5 to LeRobotDataset from $HDF5_ROOT_PATH"
    bash run.sh convert \
        --root-path "$HDF5_ROOT_PATH" \
        "${CONVERT_ARGS[@]}"
    LEROBOT_DATASET_ROOT="$(python3 - <<'PY'
from s4_pipeline.config import load_project_config
cfg = load_project_config()
print(cfg.dataset.lerobot_root / cfg.dataset.repo_id.split("/")[-1])
PY
)"
    if [[ ! -d "$LEROBOT_DATASET_ROOT" ]]; then
        echo "[PIPELINE] expected LeRobotDataset was not created: $LEROBOT_DATASET_ROOT" >&2
        exit 1
    fi
    if [[ -z "$(find "$LEROBOT_DATASET_ROOT" -mindepth 1 -maxdepth 2 -print -quit)" ]]; then
        echo "[PIPELINE] LeRobotDataset directory is empty: $LEROBOT_DATASET_ROOT" >&2
        exit 1
    fi
    echo "[PIPELINE] LeRobotDataset ready: $LEROBOT_DATASET_ROOT"
fi

if [[ "$SKIP_TRAIN" != true ]]; then
    use_smolvla_env
    TRAIN_ARGS=(--config "$TRAIN_CONFIG")
    if [[ -n "$TRAIN_STEPS" ]]; then
        TRAIN_ARGS+=(--steps "$TRAIN_STEPS")
    fi
    if [[ -n "$BATCH_SIZE" ]]; then
        TRAIN_ARGS+=(--batch-size "$BATCH_SIZE")
    fi
    if [[ -n "$SAVE_FREQ" ]]; then
        TRAIN_ARGS+=(--save-freq "$SAVE_FREQ")
    fi
    if [[ "$OVERWRITE_OUTPUT" == true ]]; then
        TRAIN_ARGS+=(--overwrite-output)
    fi
    echo "[PIPELINE] starting SmolVLA training"
    bash run.sh train "${TRAIN_ARGS[@]}"
fi

echo "[PIPELINE] complete"
