#!/usr/bin/env python
"""Write arm-control commands for the running S4 simulation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_ARM_CONTROL_FILE = Path("/tmp/s4_arm_control.json")


parser = argparse.ArgumentParser(description="Control the running S4 simulation through a JSON command file.")
subparsers = parser.add_subparsers(dest="command", required=True)

reach = subparsers.add_parser("reach-block", help="Drive the right wrist above a block.")
reach.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
reach.add_argument("--block", choices=["red", "blue"], default="blue")
reach.add_argument("--x-offset", "--reach-x-offset", type=float, default=0.0)
reach.add_argument("--y-offset", "--reach-y-offset", type=float, default=0.0)
reach.add_argument("--z-offset", "--reach-z-offset", type=float, default=0.14)
reach.add_argument("--tcp-x-offset", type=float, default=0.0)
reach.add_argument("--tcp-y-offset", type=float, default=0.0)
reach.add_argument("--tcp-z-offset", type=float, default=-0.10)
reach.add_argument("--hand", choices=["open", "close"], default="open")

hand = subparsers.add_parser("hand", help="Set right hand open/close target.")
hand.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
hand.add_argument("state", choices=["open", "close"])

test = subparsers.add_parser("test-right-arm", help="Send a direct right-arm joint target for actuator testing.")
test.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
test.add_argument("--shoulder-pitch", type=float, default=0.2)
test.add_argument("--shoulder-roll", type=float, default=-0.35)
test.add_argument("--shoulder-yaw", type=float, default=0.0)
test.add_argument("--elbow", type=float, default=-1.2)
test.add_argument("--wrist-roll", type=float, default=0.0)
test.add_argument("--wrist-pitch", type=float, default=0.0)
test.add_argument("--wrist-yaw", type=float, default=0.0)

stop = subparsers.add_parser("stop", help="Stop automatic arm control.")
stop.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)

args = parser.parse_args()


def main() -> None:
    args.file.parent.mkdir(parents=True, exist_ok=True)
    if args.command == "reach-block":
        payload = {
            "mode": "reach-block",
            "block": args.block,
            "offset": [float(args.x_offset), float(args.y_offset), float(args.z_offset)],
            "tcp_offset_wrist": [
                float(args.tcp_x_offset),
                float(args.tcp_y_offset),
                float(args.tcp_z_offset),
            ],
            "hand": args.hand,
        }
    elif args.command == "hand":
        payload = {"mode": "hand", "hand": args.state}
    elif args.command == "test-right-arm":
        payload = {
            "mode": "test-right-arm",
            "right_arm": [
                float(args.shoulder_pitch),
                float(args.shoulder_roll),
                float(args.shoulder_yaw),
                float(args.elbow),
                float(args.wrist_roll),
                float(args.wrist_pitch),
                float(args.wrist_yaw),
            ],
        }
    elif args.command == "stop":
        payload = {"mode": "idle"}
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    args.file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.file}: {payload}")


if __name__ == "__main__":
    main()
