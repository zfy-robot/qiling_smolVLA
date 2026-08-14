#!/usr/bin/env bash
set -euo pipefail

# Wait for an already-running collect-convert job, validate the dataset it
# produced, and start training only when every safety check passes.

cd "$(dirname "$0")/.."
PROJECT_ROOT="$PWD"

EXPECTED_EPISODES=200
POLL_SECONDS=60
TRAIN_STEPS=500000
BATCH_SIZE=16
SAVE_FREQ=20000
COLLECT_PID=""
DATASET_DIR=""
LOG_FILE=""
TRAIN_MODE="fresh"

usage() {
    cat <<'EOF'
Usage:
  bash scripts/wait_collect_convert_then_train.sh [options]

The script must be started while exactly one `bash run.sh collect-convert ...`
job is still running. It never starts or resumes collection itself.

Options:
  --expected-episodes N  Require exactly N converted episodes. Default: 200
  --poll-seconds N       Process polling interval. Default: 60
  --steps N              Target total training steps. Default: 500000
  --batch-size N         Training batch size. Default: 16
  --save-freq N          Checkpoint interval. Default: 20000
  --collect-pid PID      Monitor this collect_convert.sh PID instead of auto-detecting
  --dataset-dir PATH     Converted dataset path; default comes from active task config
  --log-file PATH        Combined monitor/check/train log path
  --resume               Resume training from checkpoints/last
  --overwrite-output     Delete the configured old training output and train from scratch
  -h, --help             Show this help

Safety behavior:
  * refuses zero or multiple collection jobs during auto-detection;
  * requires the converted dataset to be created/updated by the monitored run;
  * requires meta/info.json to report exactly --expected-episodes episodes;
  * runs the full `bash run.sh dataset-check` before training;
  * exits on any failure and does not start training.
EOF
}

positive_integer() {
    [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --expected-episodes) EXPECTED_EPISODES="$2"; shift 2 ;;
        --poll-seconds) POLL_SECONDS="$2"; shift 2 ;;
        --steps) TRAIN_STEPS="$2"; shift 2 ;;
        --batch-size) BATCH_SIZE="$2"; shift 2 ;;
        --save-freq) SAVE_FREQ="$2"; shift 2 ;;
        --collect-pid) COLLECT_PID="$2"; shift 2 ;;
        --dataset-dir) DATASET_DIR="$2"; shift 2 ;;
        --log-file) LOG_FILE="$2"; shift 2 ;;
        --resume)
            [[ "$TRAIN_MODE" != "overwrite" ]] || die "--resume and --overwrite-output are mutually exclusive"
            TRAIN_MODE="resume"
            shift
            ;;
        --overwrite-output)
            [[ "$TRAIN_MODE" != "resume" ]] || die "--resume and --overwrite-output are mutually exclusive"
            TRAIN_MODE="overwrite"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1 (use --help)" ;;
    esac
done

for value_name in EXPECTED_EPISODES POLL_SECONDS TRAIN_STEPS BATCH_SIZE SAVE_FREQ; do
    value="${!value_name}"
    positive_integer "$value" || die "$value_name must be a positive integer, got: $value"
done
if [[ -n "$COLLECT_PID" ]] && ! positive_integer "$COLLECT_PID"; then
    die "--collect-pid must be a positive integer, got: $COLLECT_PID"
fi

# Prevent two watcher instances from launching duplicate training jobs.
LOCK_FILE="$PROJECT_ROOT/.local/wait_collect_convert_then_train.lock"
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -n 9 || die "Another wait_collect_convert_then_train instance is already running"

if [[ -z "$LOG_FILE" ]]; then
    LOG_FILE="$PROJECT_ROOT/outputs/logs/wait_collect_then_train_$(date +%Y%m%d_%H%M%S).log"
fi
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

on_exit() {
    status=$?
    if [[ "$status" -eq 0 ]]; then
        echo "[$(date '+%F %T')] [DONE] Monitor, validation, and training completed successfully."
    else
        echo "[$(date '+%F %T')] [STOP] Exiting with status $status; training was not started or did not complete."
    fi
    echo "[LOG] $LOG_FILE"
}
trap on_exit EXIT

echo "[$(date '+%F %T')] [START] Safe wait -> validate -> train"
echo "[LOG] $LOG_FILE"

if [[ -z "$COLLECT_PID" ]]; then
    mapfile -t collect_pids < <(pgrep -f 'bash scripts/collect_convert\.sh([[:space:]]|$)' || true)
    if (( ${#collect_pids[@]} == 0 )); then
        die "No running scripts/collect_convert.sh process found. Start this watcher while collect-convert is still running."
    fi
    if (( ${#collect_pids[@]} != 1 )); then
        printf '[ERROR] Multiple collect-convert jobs found:' >&2
        printf ' %s' "${collect_pids[@]}" >&2
        printf '\n' >&2
        die "Pass the intended scripts/collect_convert.sh PID explicitly with --collect-pid PID"
    fi
    COLLECT_PID="${collect_pids[0]}"
fi

[[ -r "/proc/$COLLECT_PID/stat" ]] || die "Collection PID $COLLECT_PID is not running or is not readable"
COLLECT_START_TICKS="$(sed -E 's/^.*\) //' "/proc/$COLLECT_PID/stat" | awk '{print $20}')"
[[ -n "$COLLECT_START_TICKS" ]] || die "Could not read start identity for collection PID $COLLECT_PID"
COLLECT_CMD="$(tr '\0' ' ' < "/proc/$COLLECT_PID/cmdline")"
if [[ "$COLLECT_CMD" != *"scripts/collect_convert.sh"* ]]; then
    die "PID $COLLECT_PID is not a scripts/collect_convert.sh process: $COLLECT_CMD"
fi

if [[ -z "$DATASET_DIR" ]]; then
    CONFIG_PYTHON="${S4_ISAACLAB_PREFIX:-$HOME/miniconda3/envs/env_isaaclab}/bin/python"
    [[ -x "$CONFIG_PYTHON" ]] || die "Cannot find config Python: $CONFIG_PYTHON"
    DATASET_DIR="$($CONFIG_PYTHON - <<'PY'
from s4_pipeline.config import load_project_config
cfg = load_project_config()
print((cfg.dataset.lerobot_root / cfg.dataset.repo_id.split('/')[-1]).resolve())
PY
)"
fi
DATASET_DIR="$(realpath -m "$DATASET_DIR")"
INFO_FILE="$DATASET_DIR/meta/info.json"

dataset_signature() {
    if [[ -f "$INFO_FILE" ]]; then
        stat -c '%i:%Y:%s' "$INFO_FILE"
    else
        printf 'missing'
    fi
}

INITIAL_SIGNATURE="$(dataset_signature)"
echo "[MONITOR] PID:               $COLLECT_PID"
echo "[MONITOR] command:           $COLLECT_CMD"
echo "[MONITOR] dataset:           $DATASET_DIR"
echo "[MONITOR] initial signature: $INITIAL_SIGNATURE"
echo "[MONITOR] expected episodes: $EXPECTED_EPISODES"
echo "[MONITOR] polling every:     ${POLL_SECONDS}s"

while [[ -r "/proc/$COLLECT_PID/stat" ]]; do
    current_start_ticks="$(sed -E 's/^.*\) //' "/proc/$COLLECT_PID/stat" | awk '{print $20}')"
    if [[ "$current_start_ticks" != "$COLLECT_START_TICKS" ]]; then
        echo "[MONITOR] PID $COLLECT_PID was reused; treating the original collection process as finished."
        break
    fi
    echo "[$(date '+%F %T')] [WAIT] collect-convert is still running (PID $COLLECT_PID)"
    sleep "$POLL_SECONDS"
done

echo "[$(date '+%F %T')] [CHECK] collect-convert process has exited; verifying its output"
FINAL_SIGNATURE="$(dataset_signature)"
[[ "$FINAL_SIGNATURE" != "missing" ]] || die "Converted dataset metadata is missing: $INFO_FILE"
[[ "$FINAL_SIGNATURE" != "$INITIAL_SIGNATURE" ]] || die \
    "Dataset metadata was not updated while the monitored collection ran; refusing to train on a possibly old dataset"

ACTUAL_EPISODES="$(python3 - "$INFO_FILE" <<'PY'
import json
import sys

info = json.load(open(sys.argv[1], encoding="utf-8"))
value = info.get("total_episodes")
if not isinstance(value, int):
    raise SystemExit("meta/info.json has no integer total_episodes")
print(value)
PY
)" || die "Could not read total_episodes from $INFO_FILE"
[[ "$ACTUAL_EPISODES" -eq "$EXPECTED_EPISODES" ]] || die \
    "Converted dataset has $ACTUAL_EPISODES episodes, expected exactly $EXPECTED_EPISODES"

echo "[CHECK] metadata reports exactly $ACTUAL_EPISODES episodes"
echo "[CHECK] running full LeRobotDataset validation"
if ! bash run.sh dataset-check "$DATASET_DIR"; then
    die "Dataset validation failed; training will not start"
fi

TRAIN_ARGS=(
    --steps "$TRAIN_STEPS"
    --batch-size "$BATCH_SIZE"
    --save-freq "$SAVE_FREQ"
)
case "$TRAIN_MODE" in
    resume) TRAIN_ARGS+=(--resume) ;;
    overwrite) TRAIN_ARGS+=(--no-resume --overwrite-output) ;;
    fresh) TRAIN_ARGS+=(--no-resume) ;;
esac

echo "[$(date '+%F %T')] [TRAIN] All safety checks passed; starting training"
printf '[TRAIN] command: bash run.sh train'
printf ' %q' "${TRAIN_ARGS[@]}"
printf '\n'
echo "[TRAIN] output is displayed live and appended to: $LOG_FILE"

if ! bash run.sh train "${TRAIN_ARGS[@]}"; then
    die "Training failed"
fi

echo "[$(date '+%F %T')] [TRAIN] Training process exited successfully"
