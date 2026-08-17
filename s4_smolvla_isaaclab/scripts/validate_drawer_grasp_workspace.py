#!/usr/bin/env python3
"""Offline dense-grid IK audit for the drawer-task grasp workspace.

This checks the exact pre-grasp, grasp, and lift targets used by scripted data
collection. It intentionally does not claim to replace Isaac Sim collision
testing; its purpose is to reject unreachable, joint-limit, and numerically
ill-conditioned samples before an expensive collection run.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from s4_robot.pink_bimanual_ik import (
    DEFAULT_TCP_OFFSET_WRIST,
    PinkBimanualTcpController,
    movable_urdf_joint_names,
    quat_wxyz_from_rpy,
)
from s4_robot.s4_robot_cfg import DEFAULT_POSE, LEFT_ARM_JOINTS, RIGHT_ARM_JOINTS
from tasks.drawer_insert_close_controller import DEFAULT_SCRIPTED_CONFIG, load_scripted_config


@dataclass
class AuditResult:
    x: float
    y: float
    phase: str
    reached: bool
    position_error_m: float
    orientation_error_rad: float
    right_joint_margin_fraction: float
    right_jacobian_sigma_min: float
    right_jacobian_condition: float


class _OfflineRobot:
    def __init__(self) -> None:
        self.joint_names = movable_urdf_joint_names()


def _parse_range(raw: list[float] | None, fallback: list[float]) -> tuple[float, float]:
    value = fallback if raw is None else raw
    if len(value) != 2 or not np.all(np.isfinite(value)) or float(value[0]) >= float(value[1]):
        raise ValueError("ranges require two finite values with min < max")
    return float(value[0]), float(value[1])


def _quat_angle(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    a /= max(float(np.linalg.norm(a)), 1.0e-9)
    b /= max(float(np.linalg.norm(b)), 1.0e-9)
    return float(2.0 * np.arccos(np.clip(abs(float(np.dot(a, b))), 0.0, 1.0)))


def _right_tcp_pose(solver: PinkBimanualTcpController, q_isaac: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    pin = solver.pin
    full_q = solver._full_q_from_isaac(q_isaac)
    pin.forwardKinematics(solver.full_model, solver.full_data, full_q)
    pin.updateFramePlacements(solver.full_model, solver.full_data)
    placement = solver.full_data.oMf[solver.frame_ids[solver.right_frame]]
    rotation = np.asarray(placement.rotation, dtype=np.float64)
    position = np.asarray(placement.translation, dtype=np.float64) + rotation @ np.asarray(
        DEFAULT_TCP_OFFSET_WRIST, dtype=np.float64
    )
    quat_xyzw = np.asarray(pin.Quaternion(rotation).coeffs(), dtype=np.float64)
    quat_wxyz = quat_xyzw[[3, 0, 1, 2]]
    return position, quat_wxyz


def _right_metrics(solver: PinkBimanualTcpController, q_isaac: np.ndarray) -> tuple[float, float, float]:
    pin = solver.pin
    full_q = solver._full_q_from_isaac(q_isaac)
    pin.computeJointJacobians(solver.full_model, solver.full_data, full_q)
    pin.updateFramePlacements(solver.full_model, solver.full_data)
    frame_id = solver.frame_ids[solver.right_frame]
    placement = solver.full_data.oMf[frame_id]
    jac = np.asarray(
        pin.getFrameJacobian(
            solver.full_model,
            solver.full_data,
            frame_id,
            pin.ReferenceFrame.LOCAL_WORLD_ALIGNED,
        ),
        dtype=np.float64,
    )[:, solver.controlled_q_indices[7:]]
    tcp_offset_world = np.asarray(placement.rotation, dtype=np.float64) @ np.asarray(
        DEFAULT_TCP_OFFSET_WRIST, dtype=np.float64
    )
    jac[:3] -= solver._skew(tcp_offset_world) @ jac[3:]
    singular_values = np.linalg.svd(jac, compute_uv=False)
    sigma_min = float(singular_values[-1])
    condition = float(singular_values[0] / max(sigma_min, 1.0e-12))
    current = full_q[solver.controlled_q_indices[7:]]
    lower = solver.lower_controlled[7:]
    upper = solver.upper_controlled[7:]
    spans = np.maximum(upper - lower, 1.0e-9)
    margin = float(np.min(np.minimum(current - lower, upper - current) / spans))
    return margin, sigma_min, condition


def _solve_phase(
    solver: PinkBimanualTcpController,
    q_isaac: np.ndarray,
    target: dict[str, object],
    *,
    tolerance: float,
    orientation_tolerance: float,
    max_steps: int,
    reset_posture_reference: bool,
) -> tuple[np.ndarray, float, float, bool]:
    if reset_posture_reference:
        solver.set_posture_reference(q_isaac)
    right_ids = np.asarray(solver.isaac_order_joint_ids[7:], dtype=np.int64)
    for _ in range(max_steps):
        current_pos, current_quat = _right_tcp_pose(solver, q_isaac)
        pos_error = float(np.linalg.norm(current_pos - np.asarray(target["pos"], dtype=np.float64)))
        rot_error = _quat_angle(current_quat, np.asarray(target["quat_wxyz"], dtype=np.float64))
        if pos_error <= tolerance and rot_error <= orientation_tolerance:
            return q_isaac, pos_error, rot_error, True
        arm_target = solver.compute(q_isaac, 1.0 / 120.0, None, target)[7:]
        q_isaac[right_ids] = arm_target
    current_pos, current_quat = _right_tcp_pose(solver, q_isaac)
    pos_error = float(np.linalg.norm(current_pos - np.asarray(target["pos"], dtype=np.float64)))
    rot_error = _quat_angle(current_quat, np.asarray(target["quat_wxyz"], dtype=np.float64))
    return q_isaac, pos_error, rot_error, False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_SCRIPTED_CONFIG)
    parser.add_argument("--world-x", nargs=2, type=float)
    parser.add_argument("--world-y", nargs=2, type=float)
    parser.add_argument("--grid", nargs=2, type=int, default=[21, 21], metavar=("NX", "NY"))
    parser.add_argument("--can-world-z", type=float, default=1.1515)
    parser.add_argument("--base-world-z", type=float, default=0.98)
    parser.add_argument(
        "--right-rpy",
        nargs=3,
        type=float,
        help="Override the pre-grasp/grasp/lift right-hand RPY for posture searches.",
    )
    parser.add_argument(
        "--lift-rpy",
        nargs=3,
        type=float,
        help="Override only the lift RPY (takes precedence over --right-rpy).",
    )
    parser.add_argument("--min-joint-margin", type=float, default=0.025)
    parser.add_argument("--min-jacobian-sigma", type=float, default=0.018)
    parser.add_argument("--max-jacobian-condition", type=float, default=110.0)
    parser.add_argument(
        "--tcp-posture-gain",
        type=float,
        default=0.05,
        help="Match record_dataset.py --tcp-posture-gain.",
    )
    parser.add_argument(
        "--tcp-ik-damping",
        type=float,
        default=0.08,
        help="Match record_dataset.py --tcp-ik-damping.",
    )
    parser.add_argument(
        "--tcp-max-joint-delta",
        type=float,
        default=0.050,
        help="Match record_dataset.py --tcp-max-joint-delta.",
    )
    parser.add_argument(
        "--reset-posture-each-phase",
        action="store_true",
        help="Diagnostic only: reset the null-space posture at every phase instead of preserving pre-grasp.",
    )
    args = parser.parse_args()

    cfg = load_scripted_config(args.config)
    random_cfg = cfg["randomization"]["can_xy"]
    nominal_world = np.asarray([0.54, -0.13, args.can_world_z], dtype=np.float64)
    default_x = [nominal_world[0] + float(v) for v in random_cfg["x_range"]]
    default_y = [nominal_world[1] + float(v) for v in random_cfg["y_range"]]
    x_range = _parse_range(args.world_x, default_x)
    y_range = _parse_range(args.world_y, default_y)
    # Geometry measured from the Sektion USD at its task transform. Include
    # the scaled tomato-can footprint plus 5 mm safety margin on all edges.
    support_x = (0.4752, 1.1248)
    support_y = (-0.7248, -0.0752)
    can_radius_x = 0.03383
    can_radius_y = 0.03383 * 0.90
    edge_margin = 0.005
    safe_x = (support_x[0] + can_radius_x + edge_margin, support_x[1] - can_radius_x - edge_margin)
    safe_y = (support_y[0] + can_radius_y + edge_margin, support_y[1] - can_radius_y - edge_margin)
    if x_range[0] < safe_x[0] or x_range[1] > safe_x[1]:
        raise ValueError(f"world-x range leaves cabinet support; safe can-center interval is {safe_x}")
    if y_range[0] < safe_y[0] or y_range[1] > safe_y[1]:
        raise ValueError(f"world-y range leaves cabinet support; safe can-center interval is {safe_y}")
    nx, ny = max(int(args.grid[0]), 2), max(int(args.grid[1]), 2)

    robot = _OfflineRobot()
    solver = PinkBimanualTcpController(
        robot,
        "cpu",
        posture_gain=args.tcp_posture_gain,
        damping=args.tcp_ik_damping,
        max_joint_delta=args.tcp_max_joint_delta,
    )
    initial_q = np.asarray([DEFAULT_POSE.get(name, 0.0) for name in robot.joint_names], dtype=np.float64)
    targets = cfg["targets"]
    phases = {phase["name"]: phase for phase in cfg["phases"]}
    phase_specs = (
        ("right_pregrasp_can", "right_can_pregrasp"),
        ("right_grasp_can", "right_can_grasp"),
        ("right_lift_can", "right_can_lift"),
    )
    results: list[AuditResult] = []
    for x in np.linspace(*x_range, nx):
        for y in np.linspace(*y_range, ny):
            q = initial_q.copy()
            solver.set_posture_reference(q)
            for phase_name, target_name in phase_specs:
                target_cfg = targets[target_name]
                target_rpy = target_cfg["rpy"] if args.right_rpy is None else args.right_rpy
                if phase_name == "right_lift_can" and args.lift_rpy is not None:
                    target_rpy = args.lift_rpy
                target = {
                    "pos": [
                        x + float(target_cfg["offset"][0]),
                        y + float(target_cfg["offset"][1]),
                        args.can_world_z - args.base_world_z + float(target_cfg["offset"][2]),
                    ],
                    "quat_wxyz": quat_wxyz_from_rpy(*[float(v) for v in target_rpy]).tolist(),
                    "orientation_weight": float(target_cfg.get("orientation_weight", 1.0)),
                }
                phase_cfg = phases[phase_name]
                q, pos_error, rot_error, reached = _solve_phase(
                    solver,
                    q,
                    target,
                    tolerance=float(phase_cfg.get("tolerance", cfg["controller"]["default_tolerance"])),
                    orientation_tolerance=float(
                        phase_cfg.get(
                            "orientation_tolerance", cfg["controller"]["default_orientation_tolerance"]
                        )
                    ),
                    max_steps=int(phase_cfg.get("max_steps", 1000)),
                    reset_posture_reference=args.reset_posture_each_phase,
                )
                margin, sigma_min, condition = _right_metrics(solver, q)
                result = AuditResult(
                    x=float(x),
                    y=float(y),
                    phase=phase_name,
                    reached=reached,
                    position_error_m=pos_error,
                    orientation_error_rad=rot_error,
                    right_joint_margin_fraction=margin,
                    right_jacobian_sigma_min=sigma_min,
                    right_jacobian_condition=condition,
                )
                results.append(result)
                if not reached:
                    break

    failures = [
        result
        for result in results
        if not result.reached
        or result.right_joint_margin_fraction < args.min_joint_margin
        or result.right_jacobian_sigma_min < args.min_jacobian_sigma
        or result.right_jacobian_condition > args.max_jacobian_condition
    ]
    worst_position = max(results, key=lambda item: item.position_error_m)
    worst_condition = max(results, key=lambda item: item.right_jacobian_condition)
    worst_margin = min(results, key=lambda item: item.right_joint_margin_fraction)
    area_cm2 = (x_range[1] - x_range[0]) * (y_range[1] - y_range[0]) * 10_000.0
    print(
        f"workspace world_x=[{x_range[0]:.4f},{x_range[1]:.4f}] "
        f"world_y=[{y_range[0]:.4f},{y_range[1]:.4f}] area={area_cm2:.1f}cm^2 "
        f"points={nx * ny} phase_checks={len(results)}"
    )
    print(
        f"worst_position={worst_position.position_error_m:.6f}m "
        f"at=({worst_position.x:.4f},{worst_position.y:.4f}) phase={worst_position.phase}"
    )
    print(
        f"worst_condition={worst_condition.right_jacobian_condition:.2f} "
        f"sigma_min={worst_condition.right_jacobian_sigma_min:.5f} "
        f"at=({worst_condition.x:.4f},{worst_condition.y:.4f}) phase={worst_condition.phase}"
    )
    print(
        f"minimum_joint_margin={worst_margin.right_joint_margin_fraction:.4f} "
        f"at=({worst_margin.x:.4f},{worst_margin.y:.4f}) phase={worst_margin.phase}"
    )
    for phase_name, _ in phase_specs:
        phase_results = [result for result in results if result.phase == phase_name]
        phase_worst = max(phase_results, key=lambda item: item.position_error_m)
        print(
            f"phase={phase_name} checks={len(phase_results)} "
            f"max_position_error={phase_worst.position_error_m:.6f}m "
            f"max_condition={max(item.right_jacobian_condition for item in phase_results):.2f}"
        )
    if failures:
        print(f"FAIL unsafe_checks={len(failures)}")
        for result in failures[:20]:
            print(
                f"  ({result.x:.4f},{result.y:.4f}) {result.phase} reached={result.reached} "
                f"pos={result.position_error_m:.5f} rot={result.orientation_error_rad:.4f} "
                f"margin={result.right_joint_margin_fraction:.4f} "
                f"sigma={result.right_jacobian_sigma_min:.5f} cond={result.right_jacobian_condition:.2f}"
            )
        raise SystemExit(1)
    print("PASS all sampled pre-grasp/grasp/lift targets satisfy IK and numerical-margin thresholds")


if __name__ == "__main__":
    main()
