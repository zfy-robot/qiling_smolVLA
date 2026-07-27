#!/usr/bin/env python
"""Update the live joint-debug command JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser(description="Set joints in /tmp/s4_joint_command.json while joint-debug is running.")
parser.add_argument("assignments", nargs="+", help="Assignments like right_elbow_joint=0.3")
parser.add_argument("--control-file", type=Path, default=Path("/tmp/s4_joint_command.json"))
args = parser.parse_args()


def main() -> None:
    if args.control_file.exists():
        payload = json.loads(args.control_file.read_text(encoding="utf-8"))
    else:
        payload = {"action": [], "joints": {}}

    joints = payload.setdefault("joints", {})
    for item in args.assignments:
        if "=" not in item:
            raise SystemExit(f"Expected NAME=VALUE, got {item!r}")
        name, value = item.split("=", 1)
        joints[name] = float(value)

    args.control_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"updated {args.control_file}")


if __name__ == "__main__":
    main()
