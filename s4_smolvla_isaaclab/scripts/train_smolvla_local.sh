#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

CONFIG="${1:-configs/smolvla_s4_bimanual.yaml}"
if [[ "${1:-}" == "--"* || -z "${1:-}" ]]; then
    CONFIG="configs/smolvla_s4_bimanual.yaml"
else
    shift
fi

OVERWRITE_OUTPUT=false
RESUME_OVERRIDE=""
STEPS_OVERRIDE=""
BATCH_SIZE_OVERRIDE=""
SAVE_FREQ_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --resume)
            RESUME_OVERRIDE="true"
            shift
            ;;
        --no-resume)
            RESUME_OVERRIDE="false"
            shift
            ;;
        --overwrite-output)
            OVERWRITE_OUTPUT=true
            shift
            ;;
        --steps)
            STEPS_OVERRIDE="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE_OVERRIDE="$2"
            shift 2
            ;;
        --save-freq)
            SAVE_FREQ_OVERRIDE="$2"
            shift 2
            ;;
        --config)
            CONFIG="$2"
            shift 2
            ;;
        *)
            echo "Unknown train-smolvla option: $1" >&2
            echo "Usage: bash run.sh train-smolvla [config] [--resume|--no-resume] [--overwrite-output] [--steps N] [--batch-size N] [--save-freq N]" >&2
            exit 2
            ;;
    esac
done

if [ ! -f "$CONFIG" ]; then
    echo "Missing config: $CONFIG" >&2
    exit 1
fi

DATASET=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['dataset'])")
DATASET_ROOT=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['dataset_root'])")
OUTPUT_DIR=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['output_dir'])")
STEPS=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['steps'])")
BATCH_SIZE=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['batch_size'])")
NUM_WORKERS=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG')).get('num_workers', 0))")
DEVICE=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG')).get('device', 'cuda'))")
CHUNK_SIZE=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['chunk_size'])")
MAX_STATE_DIM=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['max_state_dim'])")
MAX_ACTION_DIM=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['max_action_dim'])")
SAVE_FREQ=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['save_freq'])")
if [ -n "$STEPS_OVERRIDE" ]; then
    STEPS="$STEPS_OVERRIDE"
fi
if [ -n "$BATCH_SIZE_OVERRIDE" ]; then
    BATCH_SIZE="$BATCH_SIZE_OVERRIDE"
fi
if [ -n "$SAVE_FREQ_OVERRIDE" ]; then
    SAVE_FREQ="$SAVE_FREQ_OVERRIDE"
fi
RESUME=$(python3 -c "import yaml; print(str(yaml.safe_load(open('$CONFIG')).get('resume', False)).lower())")
if [ -n "$RESUME_OVERRIDE" ]; then
    RESUME="$RESUME_OVERRIDE"
fi
VLM_PATH=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['vlm_model_name'])")
OPT_LR=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['optimizer_lr'])")
OPT_WD=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['optimizer_weight_decay'])")

echo "========================================"
echo "  Local S4 SmolVLA training"
echo "  Config:  $CONFIG"
echo "  Dataset: $DATASET_ROOT/$DATASET"
echo "  Output:  $OUTPUT_DIR"
echo "  Resume:  $RESUME"
echo "  Steps:   $STEPS"
echo "  Batch:   $BATCH_SIZE"
echo "  Save:    every $SAVE_FREQ steps"
echo "========================================"

if [ ! -d "$DATASET_ROOT/$DATASET" ]; then
    echo "Dataset does not exist yet: $DATASET_ROOT/$DATASET" >&2
    echo "Run: bash run.sh convert-lerobot --root-path <hdf5 file or dir>" >&2
    exit 2
fi

if [ "$OVERWRITE_OUTPUT" = true ]; then
    if [ "$RESUME" = true ]; then
        echo "--overwrite-output cannot be used together with --resume" >&2
        exit 2
    fi
    if [ -d "$OUTPUT_DIR" ]; then
        echo "[INFO] Removing existing training output: $OUTPUT_DIR"
        rm -rf "$OUTPUT_DIR"
    fi
fi

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export HUGGINGFACE_HUB_OFFLINE="${HUGGINGFACE_HUB_OFFLINE:-1}"
PROJECT_CACHE="${PROJECT_CACHE:-/home/zfy/smolVLA/s4_smolvla_isaaclab/.cache}"
export HF_HOME="${HF_HOME:-$PROJECT_CACHE/huggingface}"
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HF_HOME/hub}"
export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$HF_HOME/datasets}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"
mkdir -p "$HF_HOME" "$HF_HUB_CACHE" "$HF_DATASETS_CACHE" "$TRANSFORMERS_CACHE"

lerobot-train \
    --policy.type=smolvla \
    --dataset.repo_id="$DATASET" \
    --dataset.root="$DATASET_ROOT/$DATASET" \
    --dataset.video_backend=pyav \
    --output_dir="$OUTPUT_DIR" \
    --steps="$STEPS" \
    --batch_size="$BATCH_SIZE" \
    --log_freq=100 \
    --env_eval_freq=0 \
    --save_freq="$SAVE_FREQ" \
    --num_workers="$NUM_WORKERS" \
    --persistent_workers=false \
    --resume="$RESUME" \
    --policy.device="$DEVICE" \
    --policy.chunk_size="$CHUNK_SIZE" \
    --policy.n_action_steps="$CHUNK_SIZE" \
    --policy.n_obs_steps=1 \
    --policy.max_state_dim="$MAX_STATE_DIM" \
    --policy.max_action_dim="$MAX_ACTION_DIM" \
    --policy.resize_imgs_with_padding="[512,512]" \
    --policy.freeze_vision_encoder=true \
    --policy.train_expert_only=true \
    --policy.train_state_proj=true \
    --policy.load_vlm_weights=true \
    --policy.vlm_model_name="$VLM_PATH" \
    --policy.optimizer_lr="$OPT_LR" \
    --policy.optimizer_weight_decay="$OPT_WD" \
    --policy.optimizer_grad_clip_norm=10.0 \
    --policy.push_to_hub=false
