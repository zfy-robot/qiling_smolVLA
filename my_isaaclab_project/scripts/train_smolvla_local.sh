#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

CONFIG="${1:-configs/smolvla_s4_bimanual.yaml}"

if [ ! -f "$CONFIG" ]; then
    echo "Missing config: $CONFIG" >&2
    exit 1
fi

DATASET=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['dataset'])")
DATASET_ROOT=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['dataset_root'])")
OUTPUT_DIR=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['output_dir'])")
STEPS=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['steps'])")
BATCH_SIZE=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['batch_size'])")
CHUNK_SIZE=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['chunk_size'])")
MAX_STATE_DIM=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['max_state_dim'])")
MAX_ACTION_DIM=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['max_action_dim'])")
SAVE_FREQ=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['save_freq'])")
RESUME=$(python3 -c "import yaml; print(str(yaml.safe_load(open('$CONFIG')).get('resume', False)).lower())")
VLM_PATH=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['vlm_model_name'])")
OPT_LR=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['optimizer_lr'])")
OPT_WD=$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['optimizer_weight_decay'])")

echo "========================================"
echo "  Local S4 SmolVLA training"
echo "  Config:  $CONFIG"
echo "  Dataset: $DATASET_ROOT/$DATASET"
echo "  Output:  $OUTPUT_DIR"
echo "========================================"

if [ ! -d "$DATASET_ROOT/$DATASET" ]; then
    echo "Dataset does not exist yet: $DATASET_ROOT/$DATASET" >&2
    echo "Run: bash run.sh convert-lerobot --root-path <hdf5 file or dir>" >&2
    exit 2
fi

export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export HUGGINGFACE_HUB_OFFLINE="${HUGGINGFACE_HUB_OFFLINE:-1}"

lerobot-train \
    --policy.type=smolvla \
    --dataset.repo_id="$DATASET" \
    --dataset.root="$DATASET_ROOT/$DATASET" \
    --dataset.video_backend=pyav \
    --output_dir="$OUTPUT_DIR" \
    --steps="$STEPS" \
    --batch_size="$BATCH_SIZE" \
    --log_freq=100 \
    --eval_freq=0 \
    --save_freq="$SAVE_FREQ" \
    --num_workers=4 \
    --resume="$RESUME" \
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
