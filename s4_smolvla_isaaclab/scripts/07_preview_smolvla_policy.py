#!/usr/bin/env python
"""Offline SmolVLA policy preview on the local LeRobotDataset.

This does not run IsaacLab. It loads a trained checkpoint, feeds frames from the
converted LeRobotDataset, and compares predicted actions with recorded expert
actions. Use it before online rollout to catch checkpoint, feature, and
normalization mismatches quickly.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT_ROOT = PROJECT_ROOT / "outputs/train/smolvla_s4_right_v1/checkpoints"
DEFAULT_DATASET_ROOT = PROJECT_ROOT / "datasets/lerobot_data/s4_right_blue_cylinder_plate_v1"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/eval/offline_policy_preview.csv"
DEFAULT_HF_HOME = PROJECT_ROOT / ".cache/huggingface"
ACTION_GROUPS = {
    "left_arm": slice(0, 7),
    "left_hand": slice(7, 13),
    "right_arm": slice(13, 20),
    "right_hand": slice(20, 26),
}
RIGHT_ONLY_ACTION_GROUPS = {
    "right_arm": slice(0, 7),
    "right_hand": slice(7, 13),
}


def _set_local_hf_cache() -> None:
    os.environ.setdefault("HF_HOME", str(DEFAULT_HF_HOME))
    os.environ.setdefault("HF_HUB_CACHE", str(DEFAULT_HF_HOME / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(DEFAULT_HF_HOME / "datasets"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(DEFAULT_HF_HOME / "transformers"))


def _latest_checkpoint() -> Path:
    if not DEFAULT_CHECKPOINT_ROOT.exists():
        raise FileNotFoundError(f"Checkpoint directory not found: {DEFAULT_CHECKPOINT_ROOT}")
    candidates = sorted(p for p in DEFAULT_CHECKPOINT_ROOT.iterdir() if p.is_dir() and p.name.isdigit())
    if not candidates:
        raise FileNotFoundError(f"No numeric checkpoints found under: {DEFAULT_CHECKPOINT_ROOT}")
    return candidates[-1] / "pretrained_model"


def _resolve_checkpoint(path: str | None) -> Path:
    ckpt = Path(path).expanduser() if path else _latest_checkpoint()
    if (ckpt / "pretrained_model").exists():
        ckpt = ckpt / "pretrained_model"
    if not (ckpt / "config.json").exists():
        raise FileNotFoundError(f"SmolVLA pretrained_model config.json not found: {ckpt}")
    return ckpt


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _sample_indices(length: int, count: int) -> list[int]:
    if count <= 0:
        raise ValueError("--num-frames must be positive")
    if length <= count:
        return list(range(length))
    if count == 1:
        return [0]
    return sorted({round(i * (length - 1) / (count - 1)) for i in range(count)})


def _metrics(diff: Any) -> tuple[float, float, float]:
    import torch

    return (
        diff.abs().mean().item(),
        torch.sqrt((diff * diff).mean()).item(),
        diff.abs().max().item(),
    )


def _format_head(values: Any, limit: int = 8) -> str:
    return ",".join(f"{x:.4f}" for x in values[:limit].detach().cpu().tolist())


def _action_groups(action_dim: int) -> dict[str, slice]:
    if action_dim == 13:
        return RIGHT_ONLY_ACTION_GROUPS
    if action_dim == 26:
        return ACTION_GROUPS
    raise ValueError(f"Unsupported action dim for preview grouping: {action_dim}")


def _to_observation(item: dict[str, Any], image_key: str, task: str) -> dict[str, Any]:
    return {
        "observation.state": item["observation.state"],
        image_key: item[image_key],
        "task": task,
        "robot_type": "S4-Bimanual",
    }


def main() -> None:
    _set_local_hf_cache()

    parser = argparse.ArgumentParser(description="Preview a trained SmolVLA policy against recorded dataset frames.")
    parser.add_argument("--checkpoint", default=None, help="Checkpoint dir or pretrained_model dir. Defaults to latest.")
    parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    parser.add_argument("--repo-id", default="s4_right_blue_cylinder_plate_v1")
    parser.add_argument("--num-frames", type=int, default=20)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--mode", default="single-step", choices=["single-step", "sequential"])
    parser.add_argument("--seed", type=int, default=42, help="Seed for SmolVLA diffusion sampling.")
    args = parser.parse_args()

    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    ckpt = _resolve_checkpoint(args.checkpoint)
    cfg = _load_json(ckpt / "config.json")
    input_features = cfg.get("input_features", {})
    image_keys = [k for k, v in input_features.items() if v.get("type") == "VISUAL"]
    if not image_keys:
        raise RuntimeError(f"No visual input feature found in checkpoint config: {ckpt / 'config.json'}")
    image_key = image_keys[0]

    requested_device = torch.device(args.device)
    if requested_device.type == "cuda" and not torch.cuda.is_available():
        print("[WARN] CUDA is not available in this shell; falling back to CPU.")
        requested_device = torch.device("cpu")
    torch.manual_seed(args.seed)
    if requested_device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)

    dataset = LeRobotDataset(args.repo_id, root=args.dataset_root, video_backend="pyav")
    indices = _sample_indices(len(dataset), args.num_frames)

    print(f"[PREVIEW] checkpoint={ckpt}")
    print(f"[PREVIEW] dataset={args.dataset_root} frames={len(dataset)} sampled={len(indices)}")
    print(f"[PREVIEW] image_key={image_key} device={requested_device} mode={args.mode} seed={args.seed}")

    policy = SmolVLAPolicy.from_pretrained(str(ckpt), local_files_only=True)
    policy = policy.to(requested_device)
    policy.eval()
    preprocessor, postprocessor = make_pre_post_processors(
        policy.config,
        pretrained_path=str(ckpt),
        preprocessor_overrides={"device_processor": {"device": str(requested_device)}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )

    rows: list[dict[str, Any]] = []
    if args.mode == "sequential":
        policy.reset()

    for idx in indices:
        item = dataset[idx]
        task = item.get("task") or dataset.meta.tasks[0]
        if args.mode == "single-step":
            policy.reset()
        observation = preprocessor(_to_observation(item, image_key, task))
        expert = item["action"].to(dtype=torch.float32)
        groups = _action_groups(int(expert.numel()))
        with torch.inference_mode():
            predicted = policy.select_action(observation)
            predicted = postprocessor(predicted).squeeze(0)

        diff = predicted - expert
        mae, rmse, max_abs = _metrics(diff)
        group_metrics: dict[str, tuple[float, float, float]] = {
            name: _metrics(diff[group_slice]) for name, group_slice in groups.items()
        }
        pred_right_arm = _format_head(predicted[groups["right_arm"]], 7)
        expert_right_arm = _format_head(expert[groups["right_arm"]], 7)
        pred_right_hand = _format_head(predicted[groups["right_hand"]], 6)
        expert_right_hand = _format_head(expert[groups["right_hand"]], 6)

        row = {
            "dataset_index": int(idx),
            "episode_index": int(item.get("episode_index", -1)),
            "frame_index": int(item.get("frame_index", -1)),
            "mae": mae,
            "rmse": rmse,
            "max_abs": max_abs,
            "left_arm_mae": group_metrics.get("left_arm", (0.0, 0.0, 0.0))[0],
            "left_hand_mae": group_metrics.get("left_hand", (0.0, 0.0, 0.0))[0],
            "right_arm_mae": group_metrics["right_arm"][0],
            "right_hand_mae": group_metrics["right_hand"][0],
            "pred_right_arm": pred_right_arm,
            "expert_right_arm": expert_right_arm,
            "pred_right_hand": pred_right_hand,
            "expert_right_hand": expert_right_hand,
        }
        rows.append(row)
        print(
            f"[PREVIEW] idx={idx:05d} ep={row['episode_index']} frame={row['frame_index']} "
            f"mae={mae:.5f} rmse={rmse:.5f} max={max_abs:.5f} "
            f"group_mae(LA/LH/RA/RH)="
            f"{group_metrics.get('left_arm', (0.0, 0.0, 0.0))[0]:.4f}/"
            f"{group_metrics.get('left_hand', (0.0, 0.0, 0.0))[0]:.4f}/"
            f"{group_metrics['right_arm'][0]:.4f}/"
            f"{group_metrics['right_hand'][0]:.4f} "
            f"right_arm=[{pred_right_arm}] expert=[{expert_right_arm}] "
            f"right_hand=[{pred_right_hand}] expert=[{expert_right_hand}]"
        )

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    mean_mae = sum(row["mae"] for row in rows) / len(rows)
    mean_rmse = sum(row["rmse"] for row in rows) / len(rows)
    group_mean = {
        group: sum(row[f"{group}_mae"] for row in rows) / len(rows)
        for group in ("left_arm", "left_hand", "right_arm", "right_hand")
    }
    print(
        f"[PREVIEW] mean_mae={mean_mae:.5f} mean_rmse={mean_rmse:.5f} "
        f"group_mean_mae(LA/LH/RA/RH)="
        f"{group_mean['left_arm']:.5f}/"
        f"{group_mean['left_hand']:.5f}/"
        f"{group_mean['right_arm']:.5f}/"
        f"{group_mean['right_hand']:.5f}"
    )
    print(f"[PREVIEW] wrote {output}")


if __name__ == "__main__":
    main()
