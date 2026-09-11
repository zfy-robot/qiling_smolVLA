#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from real_vla_stack.common.config import DEFAULT_PIPELINE_CONFIG, load_pipeline_config
from real_vla_stack.common.protocol import ObservationRequest
from real_vla_stack.robot.rollout.policy_client import PolicyClient


def _first_rgb(video_root: Path) -> np.ndarray:
    import av

    videos = sorted(video_root.rglob("*.mp4"))
    if not videos:
        raise FileNotFoundError(f"no video under {video_root}")
    with av.open(str(videos[0])) as container:
        frame = next(container.decode(video=0), None)
        if frame is None:
            raise RuntimeError(f"could not decode first frame: {videos[0]}")
        return frame.to_ndarray(format="rgb24")


def _jpeg(rgb: np.ndarray) -> bytes:
    import cv2

    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return encoded.tobytes()


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end real policy server smoke")
    parser.add_argument("--config", type=Path, default=DEFAULT_PIPELINE_CONFIG)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15555)
    parser.add_argument("--startup-timeout", type=float, default=180.0)
    args = parser.parse_args()

    import pyarrow.parquet as pq

    cfg = load_pipeline_config(args.config)
    dataset = cfg.host_path_value("lerobot_root") / str(cfg.host["dataset"]["repo_id"])
    parquet = sorted((dataset / "data").rglob("*.parquet"))[0]
    state = np.asarray(
        pq.read_table(parquet, columns=["observation.state"])
        .column("observation.state")[0]
        .as_py(),
        dtype=np.float32,
    )
    images = [
        _jpeg(_first_rgb(dataset / "videos" / key))
        for key in cfg.contract.camera_keys
    ]

    command = [
        sys.executable,
        "-u",
        "-m",
        "real_vla_stack.cli",
        "serve",
        "--checkpoint",
        str(args.checkpoint),
        "--bind",
        args.bind,
        "--port",
        str(args.port),
    ]
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    ready = threading.Event()

    def stream_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            if "[REAL-VLA-SERVER] ready" in line:
                ready.set()

    output_thread = threading.Thread(target=stream_output, daemon=True)
    output_thread.start()
    try:
        deadline = time.monotonic() + args.startup_timeout
        while not ready.wait(timeout=0.25):
            if process.poll() is not None:
                raise RuntimeError(f"policy server exited before ready: rc={process.returncode}")
            if time.monotonic() >= deadline:
                raise TimeoutError("policy server did not become ready before timeout")

        client = PolicyClient(f"tcp://{args.bind}:{args.port}", timeout_ms=120_000)
        try:
            session = "s4-release-smoke"
            timestamp = time.monotonic_ns()
            first = ObservationRequest(
                cfg.contract.sha256,
                session,
                0,
                timestamp,
                cfg.contract.task,
                state,
                (timestamp, timestamp),
                rtc_inference_delay_steps=0,
                previous_accepted_request_id=-1,
                rtc_reset_history=True,
                execution_lag_rad=0.0,
            )
            response0, rtt0 = client.request(first, images[0], images[1])
            second_timestamp = timestamp + 50_000_000
            second = ObservationRequest(
                cfg.contract.sha256,
                session,
                1,
                second_timestamp,
                cfg.contract.task,
                state,
                (second_timestamp, second_timestamp),
                rtc_inference_delay_steps=1,
                previous_accepted_request_id=0,
                rtc_reset_history=False,
                execution_lag_rad=0.0,
            )
            response1, rtt1 = client.request(second, images[0], images[1])
        finally:
            client.close()

        for response in (response0, response1):
            if response.action_chunk.shape != (int(cfg.host["model"]["chunk_size"]), 8):
                raise RuntimeError(f"invalid action chunk shape: {response.action_chunk.shape}")
            if not np.isfinite(response.action_chunk).all():
                raise RuntimeError("policy server returned non-finite actions")
            if not response.rtc_enabled or response.rtc_execution_horizon != 10:
                raise RuntimeError("policy server RTC contract mismatch")
        if not response0.rtc_history_reset:
            raise RuntimeError("server did not acknowledge RTC history reset")
        if response1.rtc_source_request_id != 0:
            raise RuntimeError("server did not acknowledge the previously accepted request")
        if response1.rtc_leftover_start_index != 1:
            raise RuntimeError(
                f"unexpected RTC leftover start index: {response1.rtc_leftover_start_index}"
            )
        print(
            "[OK] real policy ZMQ protocol: "
            f"requests=2 shape={response1.action_chunk.shape} "
            f"rtt_ms=({rtt0:.1f},{rtt1:.1f}) "
            f"rtc_source={response1.rtc_source_request_id} "
            f"leftover_start={response1.rtc_leftover_start_index}",
            flush=True,
        )
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        output_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
