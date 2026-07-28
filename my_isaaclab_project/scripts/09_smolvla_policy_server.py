#!/usr/bin/env python
"""JSON-lines SmolVLA policy server for IsaacLab rollout.

The IsaacLab environment uses Python 3.11 and should stay isolated. This
server runs under the `smolvla` environment, loads the policy once, then reads
observations from stdin and writes actions to stdout.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
DEFAULT_HF_HOME = REPO_ROOT / ".cache/huggingface"


def _set_local_hf_cache() -> None:
    os.environ.setdefault("HF_HOME", str(DEFAULT_HF_HOME))
    os.environ.setdefault("HF_HUB_CACHE", str(DEFAULT_HF_HOME / "hub"))
    os.environ.setdefault("HF_DATASETS_CACHE", str(DEFAULT_HF_HOME / "datasets"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(DEFAULT_HF_HOME / "transformers"))


def _resolve_checkpoint(path: str) -> Path:
    ckpt = Path(path).expanduser()
    if (ckpt / "pretrained_model").exists():
        ckpt = ckpt / "pretrained_model"
    if not (ckpt / "config.json").exists():
        raise FileNotFoundError(f"SmolVLA pretrained_model config.json not found: {ckpt}")
    return ckpt


def _image_array_from_request(request: dict[str, Any]) -> np.ndarray:
    shape = tuple(int(x) for x in request["image_shape"])
    raw = base64.b64decode(request["image_b64"])
    image = np.frombuffer(raw, dtype=np.uint8).reshape(shape)
    if image.shape[-1] > 3:
        image = image[..., :3]
    return image.copy()


def main() -> None:
    _set_local_hf_cache()
    parser = argparse.ArgumentParser(description="Serve SmolVLA actions over JSON lines.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"[SERVER] python={sys.executable}", file=sys.stderr, flush=True)
    print(f"[SERVER] conda_prefix={os.environ.get('CONDA_PREFIX', '')}", file=sys.stderr, flush=True)

    from lerobot.policies import make_pre_post_processors, prepare_observation_for_inference
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        print("[SERVER] CUDA unavailable; using CPU", file=sys.stderr, flush=True)
        device = torch.device("cpu")
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)

    ckpt = _resolve_checkpoint(args.checkpoint)
    print(f"[SERVER] loading {ckpt}", file=sys.stderr, flush=True)
    with contextlib.redirect_stdout(sys.stderr):
        policy = SmolVLAPolicy.from_pretrained(str(ckpt), local_files_only=True)
    print("[SERVER] checkpoint loaded", file=sys.stderr, flush=True)
    print(f"[SERVER] moving policy to {device}", file=sys.stderr, flush=True)
    with contextlib.redirect_stdout(sys.stderr):
        policy = policy.to(device)
    print(f"[SERVER] policy on {device}", file=sys.stderr, flush=True)
    policy.eval()
    policy.reset()
    image_keys = [k for k, v in policy.config.input_features.items() if v.type.name == "VISUAL"]
    if not image_keys:
        raise RuntimeError("Policy checkpoint has no visual input feature.")
    image_key = image_keys[0]
    preprocessor, postprocessor = make_pre_post_processors(
        policy.config,
        pretrained_path=str(ckpt),
        preprocessor_overrides={"device_processor": {"device": str(device)}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}},
    )

    print(f"[SERVER] ready image_key={image_key}", file=sys.stderr, flush=True)
    print(json.dumps({"status": "ready", "image_key": image_key, "device": str(device)}), flush=True)

    for line in sys.stdin:
        try:
            request = json.loads(line)
            if request.get("command") == "reset":
                policy.reset()
                print(json.dumps({"status": "reset"}), flush=True)
                continue
            state = np.asarray(request["state"], dtype=np.float32)
            task = str(request.get("task", "Put the blue cylinder into the plate."))
            image = _image_array_from_request(request)
            observation = {
                "observation.state": state,
                image_key: image,
            }
            with torch.inference_mode():
                with contextlib.redirect_stdout(sys.stderr):
                    batch = prepare_observation_for_inference(
                        observation,
                        device,
                        task=task,
                        robot_type="S4-Bimanual",
                    )
                    batch = preprocessor(batch)
                    action = policy.select_action(batch)
                    action = postprocessor(action)
                    action = action.squeeze(0).detach().cpu().numpy().astype(float).tolist()
            print(json.dumps({"action": action}), flush=True)
        except Exception as exc:  # Keep server alive long enough for IsaacLab to report the error.
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}), flush=True)


if __name__ == "__main__":
    main()
