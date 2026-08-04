"""Config-driven scripted controller for the drawer insert-close task."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from s4_robot.control_mapping import ACTION_SLICES, bimanual_default_action
from s4_robot.pink_bimanual_ik import quat_wxyz_from_rpy
from s4_robot.s4_robot_cfg import DEFAULT_POSE, LEFT_ARM_JOINTS, RIGHT_ARM_JOINTS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCRIPTED_CONFIG = PROJECT_ROOT / "configs" / "tasks" / "drawer_insert_close.scripted.yaml"
OPEN_RIGHT_HAND = np.array([0.9, 0.0, 0.05, 0.05, 0.05, 0.05], dtype=np.float32)
CLOSE_RIGHT_HAND = np.array([1.0, 0.42, 0.85, 0.85, 0.85, 0.85], dtype=np.float32)
OPEN_LEFT_HAND = OPEN_RIGHT_HAND.copy()
CLOSE_LEFT_HAND = CLOSE_RIGHT_HAND.copy()


@dataclass(frozen=True)
class TcpTarget:
    pos: np.ndarray
    quat_wxyz: np.ndarray
    orientation_weight: float = 1.0

    def as_payload(self) -> dict[str, list[float]]:
        return {
            "pos": [float(x) for x in self.pos],
            "quat_wxyz": [float(x) for x in self.quat_wxyz],
            "orientation_weight": float(self.orientation_weight),
        }


@dataclass(frozen=True)
class DrawerPhase:
    name: str
    task: str
    left: TcpTarget | None
    right: TcpTarget | None
    left_hand: np.ndarray | None
    right_hand: np.ndarray | None
    left_arm_home: bool
    right_arm_home: bool
    min_steps: int
    hold_seconds: float
    max_steps: int
    tolerance: float
    orientation_tolerance: float
    drawer_open_min: float | None
    drawer_open_max: float | None


def load_scripted_config(path: Path = DEFAULT_SCRIPTED_CONFIG) -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - depends on env packaging
        raise RuntimeError("PyYAML is required for drawer scripted task config") from exc
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Drawer scripted config must be a mapping: {path}")
    drawer_cfg = data.get("randomization", {}).get("drawer_initial_open", {})
    target_open_m = drawer_cfg.get("target_open_m")
    if target_open_m is not None:
        for phase in data.get("phases", []):
            minimum = phase.get("drawer_open_min")
            if minimum is not None and float(minimum) > float(target_open_m):
                raise ValueError(
                    f"Phase {phase.get('name')!r} requires drawer_open_min={float(minimum):.3f}m "
                    f"but target_open_m={float(target_open_m):.3f}m"
                )
    return data


def _hand_target(value: str | list[float] | tuple[float, ...] | None, side: str) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.lower()
        if normalized == "open":
            return OPEN_LEFT_HAND.copy() if side == "left" else OPEN_RIGHT_HAND.copy()
        if normalized == "close":
            return CLOSE_LEFT_HAND.copy() if side == "left" else CLOSE_RIGHT_HAND.copy()
        if normalized == "hold":
            return None
        raise ValueError(f"Unknown {side}_hand target: {value!r}")
    arr = np.asarray(value, dtype=np.float32)
    if arr.shape != (6,):
        raise ValueError(f"{side}_hand target must have 6 values, got {arr.shape}")
    return arr


def _tcp_target(
    raw: dict[str, Any] | None,
    default_tolerance: float,
    anchors: dict[str, tuple[np.ndarray, np.ndarray]],
    target_specs: dict[str, dict[str, Any]],
) -> TcpTarget | None:
    del default_tolerance
    if raw is None:
        return None
    if "target" in raw:
        target_name = str(raw["target"])
        if target_name not in target_specs:
            raise ValueError(f"Unknown configured TCP target: {target_name!r}")
        raw = {**target_specs[target_name], **{key: value for key, value in raw.items() if key != "target"}}
    if "pos" in raw:
        pos = np.asarray(raw["pos"], dtype=np.float32)
    else:
        anchor_name = str(raw.get("anchor", ""))
        if anchor_name not in anchors:
            raise ValueError(f"Unknown or unavailable TCP anchor: {anchor_name!r}")
        anchor_pos, anchor_quat = anchors[anchor_name]
        offset = np.asarray(raw.get("offset", [0.0, 0.0, 0.0]), dtype=np.float32)
        if offset.shape != (3,):
            raise ValueError(f"TCP target offset must have shape (3,), got {offset.shape}")
        offset_frame = str(raw.get("offset_frame", "base_link"))
        if offset_frame == "anchor":
            from s4_robot.pink_bimanual_ik import quat_wxyz_to_matrix

            offset = quat_wxyz_to_matrix(anchor_quat) @ offset
        elif offset_frame != "base_link":
            raise ValueError(f"Unsupported TCP offset_frame: {offset_frame!r}")
        pos = np.asarray(anchor_pos, dtype=np.float32) + offset
    if pos.shape != (3,):
        raise ValueError(f"TCP target pos must have shape (3,), got {pos.shape}")
    if "quat_wxyz" in raw:
        quat = np.asarray(raw["quat_wxyz"], dtype=np.float32)
    else:
        rpy = np.asarray(raw.get("rpy", [0.0, 0.0, 0.0]), dtype=np.float32)
        if rpy.shape != (3,):
            raise ValueError(f"TCP target rpy must have shape (3,), got {rpy.shape}")
        quat = quat_wxyz_from_rpy(float(rpy[0]), float(rpy[1]), float(rpy[2]))
    norm = float(np.linalg.norm(quat))
    if norm > 1.0e-6:
        quat = quat / norm
    orientation_weight = float(np.clip(raw.get("orientation_weight", 1.0), 0.0, 1.0))
    return TcpTarget(
        pos=pos,
        quat_wxyz=quat.astype(np.float32),
        orientation_weight=orientation_weight,
    )


def _home_arm(side: str) -> np.ndarray:
    joints = LEFT_ARM_JOINTS if side == "left" else RIGHT_ARM_JOINTS
    return np.asarray([DEFAULT_POSE[name] for name in joints], dtype=np.float32)


def _pose_dist(current_pose: tuple[np.ndarray, np.ndarray] | None, target: TcpTarget | None) -> float:
    if current_pose is None or target is None:
        return 0.0
    return float(np.linalg.norm(np.asarray(current_pose[0], dtype=np.float32) - target.pos))


def _pose_angle(current_pose: tuple[np.ndarray, np.ndarray] | None, target: TcpTarget | None) -> float:
    if current_pose is None or target is None:
        return 0.0
    current_quat = np.asarray(current_pose[1], dtype=np.float64)
    target_quat = np.asarray(target.quat_wxyz, dtype=np.float64)
    current_quat /= max(float(np.linalg.norm(current_quat)), 1.0e-8)
    target_quat /= max(float(np.linalg.norm(target_quat)), 1.0e-8)
    dot = float(np.clip(abs(np.dot(current_quat, target_quat)), 0.0, 1.0))
    return float(2.0 * np.arccos(dot))


class DrawerInsertCloseController:
    """Scripted drawer task controller using independent left/right arm and hand targets."""

    def __init__(
        self,
        tcp_controller,
        config_path: Path = DEFAULT_SCRIPTED_CONFIG,
        *,
        initial_action: np.ndarray | None = None,
        anchors: dict[str, tuple[np.ndarray, np.ndarray]] | None = None,
    ):
        self.tcp_controller = tcp_controller
        self.config_path = Path(config_path)
        self.config = load_scripted_config(self.config_path)
        controller_cfg = self.config.get("controller", {})
        self.default_tolerance = float(controller_cfg.get("default_tolerance", 0.035))
        self.default_orientation_tolerance = float(controller_cfg.get("default_orientation_tolerance", 0.20))
        self.global_task = str(controller_cfg.get("task", "Open the drawer, place the object inside, and close the drawer."))
        self.anchors = anchors or {}
        self.target_specs = self.config.get("targets", {})
        if not isinstance(self.target_specs, dict):
            raise ValueError("Drawer scripted config targets must be a mapping")
        hand_cfg = self.config.get("hands", {})
        self.hand_action_hold_seconds = max(float(hand_cfg.get("action_hold_seconds", 1.0)), 0.0)
        self.hand_targets = {
            "left_open": _hand_target(hand_cfg.get("left_open", OPEN_LEFT_HAND.tolist()), "left"),
            "left_close": _hand_target(hand_cfg.get("left_close", CLOSE_LEFT_HAND.tolist()), "left"),
            "right_open": _hand_target(hand_cfg.get("right_open", OPEN_RIGHT_HAND.tolist()), "right"),
            "right_close": _hand_target(hand_cfg.get("right_close", CLOSE_RIGHT_HAND.tolist()), "right"),
        }
        self.phases = self._parse_phases(self.config.get("phases", []))
        if not self.phases:
            raise ValueError(f"No phases configured in {self.config_path}")
        self.phase_index = 0
        self.phase_steps = 0
        self._ik_posture_phase_index: int | None = None
        self.done = False
        self.failed = False
        self.failure_reason = ""
        self.action = (
            np.asarray(initial_action, dtype=np.float32).copy()
            if initial_action is not None
            else bimanual_default_action()
        )
        if self.action.shape != (26,):
            raise ValueError(f"Drawer controller action must be 26D, got {self.action.shape}")

    def _parse_phases(self, raw_phases: list[dict[str, Any]]) -> list[DrawerPhase]:
        phases: list[DrawerPhase] = []
        for raw in raw_phases:
            tolerance = float(raw.get("tolerance", self.default_tolerance))
            orientation_tolerance = float(
                raw.get("orientation_tolerance", self.default_orientation_tolerance)
            )
            left_hand = _hand_target(raw.get("left_hand"), "left")
            right_hand = _hand_target(raw.get("right_hand"), "right")
            if isinstance(raw.get("left_hand"), str) and raw["left_hand"] in {"open", "close"}:
                left_hand = self.hand_targets[f"left_{raw['left_hand']}"].copy()
            if isinstance(raw.get("right_hand"), str) and raw["right_hand"] in {"open", "close"}:
                right_hand = self.hand_targets[f"right_{raw['right_hand']}"].copy()
            commands_hand = left_hand is not None or right_hand is not None
            phases.append(
                DrawerPhase(
                    name=str(raw["name"]),
                    task=str(raw.get("task", self.global_task)),
                    left=_tcp_target(raw.get("left"), tolerance, self.anchors, self.target_specs),
                    right=_tcp_target(raw.get("right"), tolerance, self.anchors, self.target_specs),
                    left_hand=left_hand,
                    right_hand=right_hand,
                    left_arm_home=bool(raw.get("left_arm_home", False)),
                    right_arm_home=bool(raw.get("right_arm_home", False)),
                    min_steps=max(int(raw.get("min_steps", 0)), 0),
                    hold_seconds=max(
                        float(raw.get("hold_seconds", self.hand_action_hold_seconds if commands_hand else 0.0)),
                        0.0,
                    ),
                    max_steps=max(int(raw.get("max_steps", 240)), 1),
                    tolerance=max(tolerance, 0.001),
                    orientation_tolerance=max(orientation_tolerance, 0.01),
                    drawer_open_min=(
                        float(raw["drawer_open_min"]) if raw.get("drawer_open_min") is not None else None
                    ),
                    drawer_open_max=(
                        float(raw["drawer_open_max"]) if raw.get("drawer_open_max") is not None else None
                    ),
                )
            )
        return phases

    @property
    def current_phase(self) -> DrawerPhase:
        return self.phases[min(self.phase_index, len(self.phases) - 1)]

    @property
    def current_task(self) -> str:
        return self.current_phase.task

    def progress_summary(
        self,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
        drawer_open_m: float | None = None,
    ) -> str:
        """Return a compact explanation of what still blocks phase completion."""
        phase = self.current_phase
        required_steps = max(
            phase.min_steps,
            int(np.ceil(phase.hold_seconds / max(getattr(self, "_dt", 1.0 / 120.0), 1.0e-6))),
        )
        parts = [
            f"phase={self.phase_index + 1}/{len(self.phases)}:{phase.name}",
            f"step={self.phase_steps}/{phase.max_steps}",
        ]
        blockers: list[str] = []
        for side, pose, target in (
            ("L", left_pose_base, phase.left),
            ("R", right_pose_base, phase.right),
        ):
            if target is None:
                continue
            dist = _pose_dist(pose, target)
            angle = _pose_angle(pose, target)
            dist_remaining = max(dist - phase.tolerance, 0.0)
            angle_remaining = max(angle - phase.orientation_tolerance, 0.0)
            delta = target.pos - np.asarray(pose[0], dtype=np.float32) if pose is not None else np.zeros(3)
            parts.append(
                f"{side}_pos={dist:.3f}/{phase.tolerance:.3f}m(rem={dist_remaining:.3f})"
            )
            parts.append(f"{side}_dxyz=({delta[0]:+.3f},{delta[1]:+.3f},{delta[2]:+.3f})m")
            parts.append(
                f"{side}_rot={angle:.3f}/{phase.orientation_tolerance:.3f}rad(rem={angle_remaining:.3f})"
            )
            if dist_remaining > 0.0:
                blockers.append(f"{side}_position")
            if angle_remaining > 0.0:
                blockers.append(f"{side}_orientation")
        wait_steps = max(required_steps - self.phase_steps, 0)
        if wait_steps:
            wait_seconds = wait_steps * max(getattr(self, "_dt", 1.0 / 120.0), 1.0e-6)
            parts.append(f"hold_remaining={wait_seconds:.2f}s")
            blockers.append("hold")
        if phase.drawer_open_min is not None:
            current_open = float(drawer_open_m) if drawer_open_m is not None else float("nan")
            remaining = max(phase.drawer_open_min - current_open, 0.0) if np.isfinite(current_open) else float("nan")
            parts.append(f"drawer_open={current_open:.3f}/{phase.drawer_open_min:.3f}m(rem={remaining:.3f})")
            if not np.isfinite(current_open) or current_open < phase.drawer_open_min:
                blockers.append("drawer_not_open")
        if phase.drawer_open_max is not None:
            current_open = float(drawer_open_m) if drawer_open_m is not None else float("nan")
            remaining = max(current_open - phase.drawer_open_max, 0.0) if np.isfinite(current_open) else float("nan")
            parts.append(f"drawer_open={current_open:.3f}<={phase.drawer_open_max:.3f}m(rem={remaining:.3f})")
            if not np.isfinite(current_open) or current_open > phase.drawer_open_max:
                blockers.append("drawer_not_closed")
        parts.append(f"waiting={','.join(blockers) if blockers else 'ready'}")
        return " ".join(parts)

    def _advance_if_ready(
        self,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
        drawer_open_m: float | None = None,
    ) -> bool:
        phase = self.current_phase
        left_dist = _pose_dist(left_pose_base, phase.left)
        right_dist = _pose_dist(right_pose_base, phase.right)
        left_angle = _pose_angle(left_pose_base, phase.left)
        right_angle = _pose_angle(right_pose_base, phase.right)
        controlled_errors = []
        if phase.left is not None:
            controlled_errors.append((left_dist, left_angle))
        if phase.right is not None:
            controlled_errors.append((right_dist, right_angle))
        reached = not controlled_errors or all(
            dist <= phase.tolerance and angle <= phase.orientation_tolerance
            for dist, angle in controlled_errors
        )
        if phase.drawer_open_min is not None:
            reached = reached and drawer_open_m is not None and drawer_open_m >= phase.drawer_open_min
        if phase.drawer_open_max is not None:
            reached = reached and drawer_open_m is not None and drawer_open_m <= phase.drawer_open_max
        timed_out = self.phase_steps >= phase.max_steps
        required_steps = max(phase.min_steps, int(np.ceil(phase.hold_seconds / max(self._dt, 1.0e-6))))
        min_wait_done = self.phase_steps >= required_steps
        if not min_wait_done:
            return False
        if not reached and not timed_out:
            return False
        if timed_out and not reached:
            self.failed = True
            self.done = True
            self.failure_reason = (
                f"phase={phase.name} timed out after {self.phase_steps} steps "
                f"left_dist={left_dist:.3f} right_dist={right_dist:.3f} "
                f"left_angle={left_angle:.3f} right_angle={right_angle:.3f} "
                f"position_tolerance={phase.tolerance:.3f} "
                f"orientation_tolerance={phase.orientation_tolerance:.3f}"
                f" drawer_open={float(drawer_open_m) if drawer_open_m is not None else float('nan'):.3f}"
            )
            print(f"[DRAWER][FAIL] {self.failure_reason}", flush=True)
            return True
        old_name = phase.name
        self.phase_index += 1
        self.phase_steps = 0
        if self.phase_index >= len(self.phases):
            self.done = True
            self.phase_index = len(self.phases) - 1
        print(
            f"[DRAWER] phase {old_name} -> {self.current_phase.name if not self.done else 'done'} "
            f"left_dist={left_dist:.3f} right_dist={right_dist:.3f} "
            f"left_angle={left_angle:.3f} right_angle={right_angle:.3f} "
            f"reached={reached} timeout={timed_out}",
            flush=True,
        )
        return True

    def step(
        self,
        curr_joint_pos: np.ndarray,
        dt: float,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
        drawer_open_m: float | None = None,
    ) -> tuple[np.ndarray, str, str, bool]:
        if self.done:
            return self.action.copy(), self.current_phase.name, self.current_phase.task, True
        self._dt = max(float(dt), 1.0e-6)
        self._advance_if_ready(left_pose_base, right_pose_base, drawer_open_m)
        if self.done:
            return self.action.copy(), self.current_phase.name, self.current_phase.task, True
        phase = self.current_phase

        left_goal = phase.left.as_payload() if phase.left is not None else None
        right_goal = phase.right.as_payload() if phase.right is not None else None
        if left_goal is not None or right_goal is not None:
            if self._ik_posture_phase_index != self.phase_index:
                self.tcp_controller.set_posture_reference(curr_joint_pos)
                self._ik_posture_phase_index = self.phase_index
            arm_targets = self.tcp_controller.compute(curr_joint_pos, dt, left_goal, right_goal)
            self.action[ACTION_SLICES.left_arm] = arm_targets[: len(LEFT_ARM_JOINTS)]
            self.action[ACTION_SLICES.right_arm] = arm_targets[len(LEFT_ARM_JOINTS) :]
        if phase.left_arm_home:
            self.action[ACTION_SLICES.left_arm] = _home_arm("left")
        if phase.right_arm_home:
            self.action[ACTION_SLICES.right_arm] = _home_arm("right")
        if phase.left_hand is not None:
            self.action[ACTION_SLICES.left_hand] = phase.left_hand
        if phase.right_hand is not None:
            self.action[ACTION_SLICES.right_hand] = phase.right_hand

        self.phase_steps += 1
        return self.action.copy(), phase.name, phase.task, False
