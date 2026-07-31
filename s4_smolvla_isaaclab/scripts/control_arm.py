#!/usr/bin/env python
"""Write arm-control commands for the running S4 simulation."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


DEFAULT_ARM_CONTROL_FILE = Path("/tmp/s4_arm_control.json")


parser = argparse.ArgumentParser(description="Control the running S4 simulation through a JSON command file.")
subparsers = parser.add_subparsers(dest="command", required=True)

reach = subparsers.add_parser("reach-block", help="Drive the right TCP to block_pos + offset.")
reach.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
reach.add_argument("--block", choices=["red", "blue"], default="blue")
reach.add_argument("--x-offset", "--reach-x-offset", type=float, default=-0.03, help="World-frame X offset from block center.")
reach.add_argument("--y-offset", "--reach-y-offset", type=float, default=-0.05, help="World-frame Y offset from block center.")
reach.add_argument("--z-offset", "--reach-z-offset", type=float, default=0.1, help="World-frame Z offset from block center.")
reach.add_argument("--tcp-x-offset", type=float, default=0.0, help="Hand TCP offset in wrist frame.")
reach.add_argument("--tcp-y-offset", type=float, default=0.0, help="Hand TCP offset in wrist frame.")
reach.add_argument("--tcp-z-offset", type=float, default=-0.10, help="Hand TCP offset in wrist frame.")
reach.add_argument("--offset-frame", choices=["world", "wrist"], default="world", help="Frame for x/y/z offset from block center.")
reach.add_argument("--hand", choices=["open", "close"], default="open")

grasp = subparsers.add_parser("grasp-block", help="Run a right-hand pick/place smoke test.")
grasp.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
grasp.add_argument("--block", choices=["red", "blue"], default="blue")
grasp.add_argument("--x-offset", type=float, default=-0.06, help="Base X offset from block center.")
grasp.add_argument("--y-offset", type=float, default=-0.05, help="Base Y offset from block center.")
grasp.add_argument("--approach-z", type=float, default=0.1, help="Approach TCP world/wrist Z offset from block center.")
grasp.add_argument("--grasp-z", type=float, default=0.04, help="Lower TCP world/wrist Z offset from block center.")
grasp.add_argument("--lift-z", type=float, default=0.15, help="Lift TCP world/wrist Z offset from block center.")
grasp.add_argument("--place-approach-z", type=float, default=0.18, help="TCP Z offset above plate center before placing.")
grasp.add_argument("--place-z", type=float, default=0.10, help="TCP Z offset from plate center for release.")
grasp.add_argument("--place-x-offset", type=float, default=0.0, help="World/base X offset from plate center for place/release.")
grasp.add_argument(
    "--place-y-offset",
    type=float,
    default=-0.05,
    help="World/base Y offset from plate center for place/release; negative moves to robot right.",
)
grasp.add_argument("--tcp-x-offset", type=float, default=0.0, help="Hand TCP offset in wrist frame.")
grasp.add_argument("--tcp-y-offset", type=float, default=0.0, help="Hand TCP offset in wrist frame.")
grasp.add_argument("--tcp-z-offset", type=float, default=-0.10, help="Hand TCP offset in wrist frame.")
grasp.add_argument("--offset-frame", choices=["world", "wrist"], default="world", help="Frame for x/y/z offsets from block center.")
grasp.add_argument(
    "--grasp-pose",
    choices=["none", "current"],
    default="current",
    help="Pose control mode. 'current' locks approach pose, then keeps the actual grasp pose through carry/place.",
)
grasp.add_argument("--grasp-roll", type=float, default=0.0, help="Local TCP roll offset in radians, applied to the locked grasp pose.")
grasp.add_argument("--grasp-pitch", type=float, default=0.1, help="Local TCP pitch offset in radians, applied to the locked grasp pose.")
grasp.add_argument("--grasp-yaw", type=float, default=-0.20, help="Local TCP yaw offset in radians, applied to the locked grasp pose.")
grasp.add_argument("--place-roll", type=float, default=0.40, help="Extra local TCP roll offset in radians for carry-to-place/release phases.")
grasp.add_argument("--tolerance", type=float, default=0.05, help="TCP distance threshold for phase transitions.")
grasp.add_argument("--approach-steps", type=int, default=120, help="Max steps before leaving approach phase.")
grasp.add_argument(
    "--lower-steps",
    type=int,
    default=120,
    help="Steps before warning while waiting for the lower target; closing requires TCP tolerance.",
)
grasp.add_argument("--close-steps", type=int, default=70, help="Steps to hold the close command before lifting.")
grasp.add_argument("--pre-close-hold-steps", type=int, default=120, help="Steps to pause at grasp pose with the hand open before closing.")
grasp.add_argument(
    "--hand-complete-tolerance",
    type=float,
    default=0.015,
    help="Max 6D right-hand command error before arm motion may continue after close/open.",
)
grasp.add_argument("--lift-steps", type=int, default=60, help="Steps to hold the lifted block before moving to the plate.")
grasp.add_argument("--place-steps", type=int, default=150, help="Max steps before warning while moving to the plate release target.")
grasp.add_argument("--pre-release-hold-steps", type=int, default=120, help="Steps to pause at place pose with the hand closed before opening.")
grasp.add_argument("--release-steps", type=int, default=50, help="Steps to hold open hand after placing before ending.")

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

test_left = subparsers.add_parser("test-left-arm", help="Send a direct left-arm joint target for actuator testing.")
test_left.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
test_left.add_argument("--shoulder-pitch", type=float, default=0.2)
test_left.add_argument("--shoulder-roll", type=float, default=0.35)
test_left.add_argument("--shoulder-yaw", type=float, default=0.0)
test_left.add_argument("--elbow", type=float, default=-1.2)
test_left.add_argument("--wrist-roll", type=float, default=0.0)
test_left.add_argument("--wrist-pitch", type=float, default=0.0)
test_left.add_argument("--wrist-yaw", type=float, default=0.0)

bimanual = subparsers.add_parser("test-bimanual-arm", help="Send direct left/right arm joint targets.")
bimanual.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
bimanual.add_argument("--left", type=float, nargs=7, metavar=("SP", "SR", "SY", "E", "WR", "WP", "WY"))
bimanual.add_argument("--right", type=float, nargs=7, metavar=("SP", "SR", "SY", "E", "WR", "WP", "WY"))

tcp_pose = subparsers.add_parser(
    "tcp-pose",
    help="Send one or two wrist/TCP pose targets in robot base_link frame, solved by Pink IK.",
)
tcp_pose.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
tcp_pose.add_argument("--frame", choices=["base_link"], default="base_link")
tcp_pose.add_argument("--left-pos", type=float, nargs=3, metavar=("X", "Y", "Z"))
tcp_pose.add_argument("--left-rpy", type=float, nargs=3, metavar=("R", "P", "Y"))
tcp_pose.add_argument("--left-quat", type=float, nargs=4, metavar=("W", "X", "Y", "Z"))
tcp_pose.add_argument("--right-pos", type=float, nargs=3, metavar=("X", "Y", "Z"))
tcp_pose.add_argument("--right-rpy", type=float, nargs=3, metavar=("R", "P", "Y"))
tcp_pose.add_argument("--right-quat", type=float, nargs=4, metavar=("W", "X", "Y", "Z"))

stop = subparsers.add_parser("stop", help="Stop automatic arm control.")
stop.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)

reset_scene = subparsers.add_parser("reset-scene", aliases=["reload-scene"], help="Reset robot, task objects, camera, and control state in the running simulation.")
reset_scene.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)

diagnose = subparsers.add_parser("diagnose-right-arm", help="Run right-arm kinematics/Jacobian/hold diagnostics in the running simulation.")
diagnose.add_argument("--file", type=Path, default=DEFAULT_ARM_CONTROL_FILE)
diagnose.add_argument("--eps", type=float, default=0.01, help="Joint finite-difference step in radians.")
diagnose.add_argument("--hold-steps", type=int, default=60, help="Number of simulation steps for passive hold-drift test.")
diagnose.add_argument("--drive-steps", type=int, default=30, help="Simulation steps for each positive joint-target response test.")

args = parser.parse_args()


def quat_from_rpy(roll: float, pitch: float, yaw: float) -> list[float]:
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)
    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    return [
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    ]


def arm_joint_payload(args_obj) -> list[float]:
    return [
        float(args_obj.shoulder_pitch),
        float(args_obj.shoulder_roll),
        float(args_obj.shoulder_yaw),
        float(args_obj.elbow),
        float(args_obj.wrist_roll),
        float(args_obj.wrist_pitch),
        float(args_obj.wrist_yaw),
    ]


def tcp_side_payload(pos, rpy, quat):
    if pos is None:
        return None
    if quat is None:
        quat = quat_from_rpy(*(rpy or [0.0, 0.0, 0.0]))
    return {
        "pos": [float(x) for x in pos],
        "quat_wxyz": [float(x) for x in quat],
    }


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
            "offset_frame": args.offset_frame,
            "hand": args.hand,
        }
    elif args.command == "grasp-block":
        payload = {
            "mode": "grasp-block",
            "block": args.block,
            "base_offset": [float(args.x_offset), float(args.y_offset)],
            "approach_z": float(args.approach_z),
            "grasp_z": float(args.grasp_z),
            "lift_z": float(args.lift_z),
            "place_approach_z": float(args.place_approach_z),
            "place_z": float(args.place_z),
            "place_offset": [float(args.place_x_offset), float(args.place_y_offset)],
            "tcp_offset_wrist": [
                float(args.tcp_x_offset),
                float(args.tcp_y_offset),
                float(args.tcp_z_offset),
            ],
            "offset_frame": args.offset_frame,
            "grasp_pose": args.grasp_pose,
            "grasp_rpy": [float(args.grasp_roll), float(args.grasp_pitch), float(args.grasp_yaw)],
            "place_rpy": [float(args.place_roll), 0.0, 0.0],
            "tolerance": float(args.tolerance),
            "approach_steps": int(args.approach_steps),
            "lower_steps": int(args.lower_steps),
            "close_steps": int(args.close_steps),
            "pre_close_hold_steps": int(args.pre_close_hold_steps),
            "hand_complete_tolerance": float(args.hand_complete_tolerance),
            "lift_steps": int(args.lift_steps),
            "place_steps": int(args.place_steps),
            "pre_release_hold_steps": int(args.pre_release_hold_steps),
            "release_steps": int(args.release_steps),
        }
    elif args.command == "hand":
        payload = {"mode": "hand", "hand": args.state}
    elif args.command == "test-right-arm":
        payload = {
            "mode": "test-right-arm",
            "right_arm": arm_joint_payload(args),
        }
    elif args.command == "test-left-arm":
        payload = {
            "mode": "test-left-arm",
            "left_arm": arm_joint_payload(args),
        }
    elif args.command == "test-bimanual-arm":
        if args.left is None and args.right is None:
            raise SystemExit("test-bimanual-arm requires --left and/or --right")
        payload = {
            "mode": "test-bimanual-arm",
            "left_arm": None if args.left is None else [float(x) for x in args.left],
            "right_arm": None if args.right is None else [float(x) for x in args.right],
        }
    elif args.command == "tcp-pose":
        left = tcp_side_payload(args.left_pos, args.left_rpy, args.left_quat)
        right = tcp_side_payload(args.right_pos, args.right_rpy, args.right_quat)
        if left is None and right is None:
            raise SystemExit("tcp-pose requires --left-pos and/or --right-pos")
        payload = {
            "mode": "tcp-pose",
            "frame": args.frame,
            "left": left,
            "right": right,
        }
    elif args.command == "stop":
        payload = {"mode": "idle"}
    elif args.command in {"reset-scene", "reload-scene"}:
        payload = {"mode": "reset-scene"}
    elif args.command == "diagnose-right-arm":
        payload = {
            "mode": "diagnose-right-arm",
            "eps": float(args.eps),
            "hold_steps": int(args.hold_steps),
            "drive_steps": int(args.drive_steps),
        }
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    args.file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {args.file}: {payload}")


if __name__ == "__main__":
    main()
