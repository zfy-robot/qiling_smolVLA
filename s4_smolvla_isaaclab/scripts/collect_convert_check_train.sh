#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."

EPISODES=100
EPISODE_TIMEOUT_S=300
RESET_SETTLE_S=2.0
RECORD_EVERY_N=6
RANDOM_SEED=42
HEADLESS=true
RUN_DIR=""
HDF5_FILE=""
RESUME_COLLECTION=false
OVERWRITE_DATASET=false
OVERWRITE_TRAINING_OUTPUT=false
RESUME_TRAINING=false
ALLOW_SKIPPED_GRID_CELLS=false
MAX_FAILED_ATTEMPTS=""
TRAIN_CONFIG=""
TRAIN_STEPS=""
TRAIN_BATCH_SIZE=""
TRAIN_SAVE_FREQ=""
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage:
  bash run.sh collect-train [options]

Safely run: collect HDF5 -> validate HDF5/failure report -> convert -> validate
LeRobotDataset -> train. Any failed check stops the pipeline before training.

Collection:
  --episodes N                    Successful episodes. Default: 100
  --episode-timeout-s S           Attempt timeout. Default: 300
  --reset-settle-s S              Reset settling time. Default: 2.0
  --record-every-n N              Must be 6 for the configured 20 Hz dataset
  --random-seed N                 Default: 42
  --headless, --no-render         Headless camera rendering. Default
  --render                        Show Isaac Sim
  --run-dir PATH                  Run artifacts/log directory
  --hdf5-file PATH                Exact staging HDF5 path
  --resume-collection             Continue the exact --hdf5-file

Safety gates:
  --max-failed-attempts N         Abort collection immediately if exceeded;
                                  default: 0 (strict failure-free collection)
  --allow-skipped-grid-cells      Permit training when a 3-point grid cell was skipped
  --overwrite-dataset             Explicitly replace existing converted dataset

Training:
  --config PATH                   Training config (default: active task config)
  --steps N                       Override total training steps
  --batch-size N                  Override batch size
  --save-freq N                   Override checkpoint frequency
  --overwrite-training-output     Explicitly start fresh and replace old training output
  --resume-training               Resume a complete last checkpoint

Other:
  --dry-run                       Print resolved paths and commands only
  -h, --help                      Show help

Example (fresh collection and training):
  bash run.sh collect-train --episodes 200 --overwrite-dataset \
    --overwrite-training-output --headless
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --episodes|--num-episodes) EPISODES="$2"; shift 2 ;;
        --episode-timeout-s) EPISODE_TIMEOUT_S="$2"; shift 2 ;;
        --reset-settle-s) RESET_SETTLE_S="$2"; shift 2 ;;
        --record-every-n) RECORD_EVERY_N="$2"; shift 2 ;;
        --random-seed) RANDOM_SEED="$2"; shift 2 ;;
        --headless|--no-render) HEADLESS=true; shift ;;
        --render) HEADLESS=false; shift ;;
        --run-dir) RUN_DIR="$2"; shift 2 ;;
        --hdf5-file) HDF5_FILE="$2"; shift 2 ;;
        --resume-collection) RESUME_COLLECTION=true; shift ;;
        --max-failed-attempts) MAX_FAILED_ATTEMPTS="$2"; shift 2 ;;
        --allow-skipped-grid-cells) ALLOW_SKIPPED_GRID_CELLS=true; shift ;;
        --overwrite-dataset) OVERWRITE_DATASET=true; shift ;;
        --config) TRAIN_CONFIG="$2"; shift 2 ;;
        --steps) TRAIN_STEPS="$2"; shift 2 ;;
        --batch-size) TRAIN_BATCH_SIZE="$2"; shift 2 ;;
        --save-freq) TRAIN_SAVE_FREQ="$2"; shift 2 ;;
        --overwrite-training-output) OVERWRITE_TRAINING_OUTPUT=true; shift ;;
        --resume-training) RESUME_TRAINING=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown collect-train option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

for value_name in EPISODES RECORD_EVERY_N RANDOM_SEED; do
    value="${!value_name}"
    if ! [[ "$value" =~ ^[0-9]+$ ]] || [[ "$value_name" != RANDOM_SEED && "$value" -eq 0 ]]; then
        echo "$value_name must be a positive integer (RANDOM_SEED may be zero): $value" >&2
        exit 2
    fi
done
if [[ "$RECORD_EVERY_N" -ne 6 ]]; then
    echo "--record-every-n must be 6: the simulator is 120 Hz and the dataset/training contract is 20 Hz." >&2
    exit 2
fi
if [[ -z "$MAX_FAILED_ATTEMPTS" ]]; then
    MAX_FAILED_ATTEMPTS=0
fi
if ! [[ "$MAX_FAILED_ATTEMPTS" =~ ^[0-9]+$ ]]; then
    echo "--max-failed-attempts must be a non-negative integer" >&2
    exit 2
fi
if [[ "$OVERWRITE_TRAINING_OUTPUT" == true && "$RESUME_TRAINING" == true ]]; then
    echo "Use either --overwrite-training-output or --resume-training, not both." >&2
    exit 2
fi
if [[ "$RESUME_COLLECTION" == true && -z "$HDF5_FILE" ]]; then
    echo "--resume-collection requires --hdf5-file so the source is unambiguous." >&2
    exit 2
fi

CONFIG_PYTHON="${S4_ISAACLAB_PREFIX:-$HOME/miniconda3/envs/env_isaaclab}/bin/python"
if [[ ! -x "$CONFIG_PYTHON" ]]; then
    echo "IsaacLab environment Python not found: $CONFIG_PYTHON" >&2
    exit 2
fi
mapfile -t CONFIG_VALUES < <("$CONFIG_PYTHON" - <<'PY'
from s4_pipeline.config import load_project_config
from s4_pipeline.paths import SMOLVLA_CONFIG_PATH
c = load_project_config()
print(c.dataset.staging_root)
print(c.dataset.lerobot_root)
print(c.dataset.repo_id.split("/")[-1])
print(c.dataset.task_id)
print(c.dataset.fps)
print(SMOLVLA_CONFIG_PATH)
PY
)
STAGING_ROOT="${CONFIG_VALUES[0]}"
DATASET_ROOT="${CONFIG_VALUES[1]}"
DATASET_NAME="${CONFIG_VALUES[2]}"
TASK_ID="${CONFIG_VALUES[3]}"
DATASET_FPS="${CONFIG_VALUES[4]}"
if [[ -z "$TRAIN_CONFIG" ]]; then
    TRAIN_CONFIG="${CONFIG_VALUES[5]}"
fi
if [[ "$DATASET_FPS" -ne 20 ]]; then
    echo "Configured dataset fps is $DATASET_FPS, but this guarded script expects 20 Hz." >&2
    exit 2
fi

if [[ -n "$HDF5_FILE" && -z "$RUN_DIR" ]]; then
    RUN_DIR="$(dirname "$HDF5_FILE")"
elif [[ -z "$RUN_DIR" ]]; then
    RUN_DIR="$STAGING_ROOT/safe_pipeline_$(date +%Y%m%d_%H%M%S)"
fi
if [[ -z "$HDF5_FILE" ]]; then
    HDF5_FILE="$RUN_DIR/${TASK_ID}_scripted.hdf5"
fi
FAILURE_LOG="$RUN_DIR/collection_failures.jsonl"
FAILURE_SUMMARY="$RUN_DIR/collection_failure_summary.json"
PIPELINE_LOG="$RUN_DIR/pipeline.log"
DATASET_DIR="$DATASET_ROOT/$DATASET_NAME"

if [[ ! -f "$TRAIN_CONFIG" ]]; then
    echo "Training config does not exist: $TRAIN_CONFIG" >&2
    exit 2
fi
TRAIN_DATASET="$(python3 scripts/config_value.py training dataset --config "$TRAIN_CONFIG")"
TRAIN_DATASET_ROOT="$(python3 scripts/config_value.py training dataset_root --config "$TRAIN_CONFIG")"
TRAIN_OUTPUT_DIR="$(python3 scripts/config_value.py training output_dir --config "$TRAIN_CONFIG")"
if [[ "$TRAIN_DATASET" != "$DATASET_NAME" || "$TRAIN_DATASET_ROOT/$TRAIN_DATASET" != "$DATASET_DIR" ]]; then
    echo "Training config dataset does not match conversion target." >&2
    echo "  converted: $DATASET_DIR" >&2
    echo "  training:  $TRAIN_DATASET_ROOT/$TRAIN_DATASET" >&2
    exit 2
fi

if [[ "$RESUME_COLLECTION" == true ]]; then
    [[ -f "$HDF5_FILE" ]] || { echo "Resume HDF5 missing: $HDF5_FILE" >&2; exit 2; }
else
    [[ ! -e "$HDF5_FILE" ]] || { echo "Refusing to overwrite HDF5: $HDF5_FILE" >&2; exit 2; }
    [[ ! -e "$FAILURE_LOG" && ! -e "$FAILURE_SUMMARY" ]] || {
        echo "Refusing to overwrite existing failure records in $RUN_DIR" >&2; exit 2;
    }
fi
if [[ -e "$DATASET_DIR" && "$OVERWRITE_DATASET" != true ]]; then
    echo "Converted dataset already exists: $DATASET_DIR" >&2
    echo "Pass --overwrite-dataset explicitly, or move it first." >&2
    exit 2
fi
if [[ -e "$TRAIN_OUTPUT_DIR" && "$OVERWRITE_TRAINING_OUTPUT" != true && "$RESUME_TRAINING" != true ]]; then
    echo "Training output already exists: $TRAIN_OUTPUT_DIR" >&2
    echo "Pass --overwrite-training-output or --resume-training explicitly." >&2
    exit 2
fi

mkdir -p "$RUN_DIR"
exec 9>"$RUN_DIR/.pipeline.lock"
if ! flock -n 9; then
    echo "Another pipeline owns the lock: $RUN_DIR/.pipeline.lock" >&2
    exit 2
fi

CURRENT_STAGE="preflight"
pipeline_error() {
    code=$?
    printf '[FAILED] stage=%s exit_code=%s time=%s\n' "$CURRENT_STAGE" "$code" "$(date --iso-8601=seconds)" | tee -a "$PIPELINE_LOG"
    printf '[FAILED] no later stage was started; log=%s\n' "$PIPELINE_LOG" | tee -a "$PIPELINE_LOG"
    exit "$code"
}
trap pipeline_error ERR

log() {
    printf '%s\n' "$*" | tee -a "$PIPELINE_LOG"
}

run_cmd() {
    {
        printf '[COMMAND]'
        printf ' %q' "$@"
        printf '\n'
    } | tee -a "$PIPELINE_LOG"
    if [[ "$DRY_RUN" != true ]]; then
        "$@" 2>&1 | tee -a "$PIPELINE_LOG"
    fi
}

{
    echo "============================================================"
    echo "S4 guarded collect -> convert -> check -> train"
    echo "run_dir=$RUN_DIR"
    echo "hdf5=$HDF5_FILE"
    echo "failure_log=$FAILURE_LOG"
    echo "failure_summary=$FAILURE_SUMMARY"
    echo "dataset=$DATASET_DIR"
    echo "training_output=$TRAIN_OUTPUT_DIR"
    echo "episodes=$EPISODES max_failed_attempts=$MAX_FAILED_ATTEMPTS"
    echo "started=$(date --iso-8601=seconds) dry_run=$DRY_RUN"
    echo "============================================================"
} | tee -a "$PIPELINE_LOG"

RECORD_ARGS=(bash run.sh record --output "$HDF5_FILE" --episodes "$EPISODES"
    --episode-timeout-s "$EPISODE_TIMEOUT_S" --reset-settle-s "$RESET_SETTLE_S"
    --record-every-n "$RECORD_EVERY_N" --random-seed "$RANDOM_SEED"
    --failure-log "$FAILURE_LOG" --failure-summary "$FAILURE_SUMMARY"
    --max-failed-attempts "$MAX_FAILED_ATTEMPTS")
[[ "$HEADLESS" == true ]] && RECORD_ARGS+=(--headless)
[[ "$RESUME_COLLECTION" == true ]] && RECORD_ARGS+=(--resume)

CURRENT_STAGE="collection"
log "[1/5] Collecting successful HDF5 episodes"
run_cmd "${RECORD_ARGS[@]}"

CHECK_FAILURE_ARGS=(--failure-summary "$FAILURE_SUMMARY" --max-failed-attempts "$MAX_FAILED_ATTEMPTS")
[[ "$ALLOW_SKIPPED_GRID_CELLS" == true ]] && CHECK_FAILURE_ARGS+=(--allow-skipped-grid-cells)
CURRENT_STAGE="hdf5_validation"
log "[2/5] Validating HDF5, episode count, grid metadata, and failure report"
run_cmd bash run.sh dataset-check "$HDF5_FILE" --hdf5 --expected-episodes "$EPISODES" "${CHECK_FAILURE_ARGS[@]}"

CURRENT_STAGE="conversion"
log "[3/5] Converting to LeRobotDataset"
CONVERT_ARGS=(bash run.sh convert --root-path "$HDF5_FILE" --output-root "$DATASET_ROOT" --repo-id "$DATASET_NAME")
[[ "$OVERWRITE_DATASET" == true ]] && CONVERT_ARGS+=(--overwrite)
run_cmd "${CONVERT_ARGS[@]}"

CURRENT_STAGE="lerobot_validation"
log "[4/5] Validating converted dataset before training"
run_cmd bash run.sh dataset-check "$DATASET_DIR" --expected-episodes "$EPISODES"

CURRENT_STAGE="training"
log "[5/5] Starting training (live output follows)"
TRAIN_ARGS=(bash run.sh train --config "$TRAIN_CONFIG")
[[ "$RESUME_TRAINING" == true ]] && TRAIN_ARGS+=(--resume)
[[ "$OVERWRITE_TRAINING_OUTPUT" == true ]] && TRAIN_ARGS+=(--no-resume --overwrite-output)
[[ -n "$TRAIN_STEPS" ]] && TRAIN_ARGS+=(--steps "$TRAIN_STEPS")
[[ -n "$TRAIN_BATCH_SIZE" ]] && TRAIN_ARGS+=(--batch-size "$TRAIN_BATCH_SIZE")
[[ -n "$TRAIN_SAVE_FREQ" ]] && TRAIN_ARGS+=(--save-freq "$TRAIN_SAVE_FREQ")
run_cmd "${TRAIN_ARGS[@]}"

CURRENT_STAGE="complete"
if [[ "$DRY_RUN" == true ]]; then
    log "[DRY-RUN COMPLETE] no collection, conversion, validation, or training command was executed"
else
    log "[COMPLETE] training exited successfully at $(date --iso-8601=seconds)"
fi
log "[COMPLETE] pipeline_log=$PIPELINE_LOG"
log "[COMPLETE] failure_summary=$FAILURE_SUMMARY"
