#!/usr/bin/env python
"""Create an offline policy visualization video on a recorded episode."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_CHECKPOINT_ROOT = REPO_ROOT / "outputs/train/smolvla_s4_bimanual_v0/checkpoints"
DEFAULT_DATASET_ROOT = REPO_ROOT / "datasets/lerobot_data/s4_bimanual_red_blue_plate_v0"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/eval/policy_visualization.mp4"
DEFAULT_HF_HOME = REPO_ROOT / ".cache/huggingface"
RIGHT_ARM = slice(13, 20)
RIGHT_HAND = slice(20, 26)


def _set_local_hf_cache() -> None:
    os.environ.setdefault("HF_HOME", str(DEFAULT_HF_HOME))
    os.environ.setdefault("HF_HUB_CACHE", str(DEFAULT_HF_HOME / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(DEFAULT_HF_HOME / "datasets"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(DEFAULT_HF_HOME / "transformers"))


def _latest_checkpoint() -> Path:
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


def _episode_indices(dataset: Any, episode_index: int, start_frame: int, max_frames: int) -> list[int]:
    indices: list[int] = []
    for idx in range(len(dataset)):
        item = dataset[idx]
        ep = int(item.get("episode_index", -1))
        frame = int(item.get("frame_index", -1))
        if ep == episode_index and frame >= start_frame:
            indices.append(idx)
            if len(indices) >= max_frames:
                break
    if not indices:
        raise ValueError(f"No frames found for episode_index={episode_index}, start_frame={start_frame}")
    return indices


def _to_observation(item: dict[str, Any], image_key: str, task: str) -> dict[str, Any]:
    return {
        "observation.state": item["observation.state"],
        image_key: item[image_key],
        "task": task,
        "robot_type": "S4-Bimanual",
    }


def _image_uint8(image: Any) -> Any:
    import numpy as np

    arr = image.detach().cpu().numpy()
    if arr.ndim == 3 and arr.shape[0] in {1, 3}:
        arr = arr.transpose(1, 2, 0)
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0.0, 1.0)
        arr = (arr * 255.0).astype(np.uint8)
    if arr.shape[-1] > 3:
        arr = arr[..., :3]
    return arr


def _draw_bars(draw: Any, x: int, y: int, title: str, pred: list[float], expert: list[float], lo: float, hi: float) -> int:
    draw.text((x, y), title, fill=(255, 255, 255))
    y += 18
    width = 180
    row_h = 16
    zero = x + int((0.0 - lo) / (hi - lo) * width)
    for i, (p, e) in enumerate(zip(pred, expert, strict=True)):
        yy = y + i * row_h
        draw.line((x, yy + 8, x + width, yy + 8), fill=(70, 70, 70))
        draw.line((zero, yy + 3, zero, yy + 13), fill=(130, 130, 130))
        px = x + int((max(lo, min(hi, p)) - lo) / (hi - lo) * width)
        ex = x + int((max(lo, min(hi, e)) - lo) / (hi - lo) * width)
        draw.rectangle((min(zero, ex), yy + 3, max(zero, ex), yy + 7), fill=(70, 170, 255))
        draw.rectangle((min(zero, px), yy + 9, max(zero, px), yy + 13), fill=(255, 170, 60))
        draw.text((x + width + 8, yy), f"{i}: p={p:+.2f} e={e:+.2f}", fill=(230, 230, 230))
    return y + len(pred) * row_h + 8


def _draw_frame(image: Any, info: dict[str, Any], pred: Any, expert: Any) -> Any:
    import numpy as np
    import torch
    from PIL import Image, ImageDraw

    base = Image.fromarray(_image_uint8(image)).convert("RGB")
    panel_w = 430
    canvas = Image.new("RGB", (base.width + panel_w, base.height), (18, 18, 18))
    canvas.paste(base, (0, 0))
    draw = ImageDraw.Draw(canvas)
    x = base.width + 14
    y = 12
    diff = pred - expert
    mae = diff.abs().mean().item()
    ra_mae = diff[RIGHT_ARM].abs().mean().item()
    rh_mae = diff[RIGHT_HAND].abs().mean().item()
    draw.text((x, y), "SmolVLA offline policy visualization", fill=(255, 255, 255))
    y += 22
    draw.text((x, y), f"episode={info['episode']} frame={info['frame']} idx={info['idx']}", fill=(220, 220, 220))
    y += 18
    draw.text((x, y), f"MAE all={mae:.4f} right_arm={ra_mae:.4f} right_hand={rh_mae:.4f}", fill=(220, 220, 220))
    y += 26
    draw.text((x, y), "blue=expert  orange=policy", fill=(200, 200, 200))
    y += 24
    pred_list = pred.detach().cpu().tolist()
    expert_list = expert.detach().cpu().tolist()
    y = _draw_bars(draw, x, y, "right_arm action[13:20]", pred_list[13:20], expert_list[13:20], -1.8, 1.8)
    _draw_bars(draw, x, y, "right_hand action[20:26]", pred_list[20:26], expert_list[20:26], -0.2, 1.2)
    return np.asarray(canvas)


def _write_video(frames: list[Any], output: Path, fps: int) -> None:
    import av

    output.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(output), mode="w")
    stream = container.add_stream("h264", rate=fps)
    stream.width = frames[0].shape[1]
    stream.height = frames[0].shape[0]
    stream.pix_fmt = "yuv420p"
    for frame_np in frames:
        frame = av.VideoFrame.from_ndarray(frame_np, format="rgb24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def main() -> None:
    _set_local_hf_cache()
    parser = argparse.ArgumentParser(description="Render an offline SmolVLA policy visualization video.")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--dataset-root", default=str(DEFAULT_DATASET_ROOT))
    parser.add_argument("--repo-id", default="s4_bimanual_red_blue_plate_v0")
    parser.add_argument("--episode-index", type=int, default=0)
    parser.add_argument("--start-frame", type=int, default=0)
    parser.add_argument("--max-frames", type=int, default=360)
    parser.add_argument("--fps", type=int, default=20)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        print("[WARN] CUDA is not available in this shell; falling back to CPU.")
        device = torch.device("cpu")
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)

    ckpt = _resolve_checkpoint(args.checkpoint)
    dataset = LeRobotDataset(args.repo_id, root=args.dataset_root, video_backend="pyav")
    indices = _episode_indices(dataset, args.episode_index, args.start_frame, args.max_frames)

    policy = SmolVLAPolicy.from_pretrained(str(ckpt), local_files_only=True).to(device)
    policy.eval()
    policy.reset()
    preprocessor, postprocessor = make_pre_post_processors(
        policy.config,
        pretrained_path=str(ckpt),
        preprocessor_overrides={"device_processor": {"device": str(device)}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )
    image_keys = [k for k in dataset.features if k.startswith("observation.images.")]
    if not image_keys:
        raise RuntimeError("No observation.images.* feature found in dataset.")
    image_key = image_keys[0]

    print(f"[VIS] checkpoint={ckpt}")
    print(f"[VIS] dataset={args.dataset_root} episode={args.episode_index} frames={len(indices)}")
    print(f"[VIS] image_key={image_key} device={device}")

    frames = []
    for n, idx in enumerate(indices):
        item = dataset[idx]
        task = item.get("task") or dataset.meta.tasks[0]
        observation = preprocessor(_to_observation(item, image_key, task))
        expert = item["action"].to(dtype=torch.float32)
        with torch.inference_mode():
            pred = policy.select_action(observation)
            pred = postprocessor(pred).squeeze(0)
        info = {
            "idx": int(idx),
            "episode": int(item.get("episode_index", -1)),
            "frame": int(item.get("frame_index", -1)),
        }
        frames.append(_draw_frame(item[image_key], info, pred, expert))
        if (n + 1) % 50 == 0:
            print(f"[VIS] rendered {n + 1}/{len(indices)} frames")

    output = Path(args.output).expanduser()
    _write_video(frames, output, args.fps)
    print(f"[VIS] wrote {output}")


if __name__ == "__main__":
    main()
