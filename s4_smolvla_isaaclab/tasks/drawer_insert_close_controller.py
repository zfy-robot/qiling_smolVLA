"""Config-driven scripted controller for the drawer insert-close task."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    right_home_after_tcp_reached: bool
    min_steps: int
    hold_seconds: float
    max_steps: int
    tolerance: float
    orientation_tolerance: float
    drawer_open_min: float | None
    drawer_open_max: float | None
    require_tcp_reached: bool
    require_left_tcp_reached: bool
    require_right_tcp_reached: bool
    close_drawer_from_current: bool
    drawer_close_target_open_m: float
    drawer_close_overtravel_m: float
    hold_current_left_pose: bool
    left_offset_from_current: np.ndarray | None
    right_offset_from_current: np.ndarray | None
    target_alpha: float | None
    max_joint_step: float | None


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
    success_cfg = data.get("success", {})
    if success_cfg:
        drawer_open_abs_max = float(success_cfg.get("drawer_open_abs_max", 0.04))
        if drawer_open_abs_max <= 0.0:
            raise ValueError("success.drawer_open_abs_max must be positive")
        can_cfg = success_cfg.get("can_world_z", {})
        min_z = float(can_cfg.get("min_m", 1.00))
        max_z = float(can_cfg.get("max_m", 1.04))
        if not np.isfinite(min_z) or not np.isfinite(max_z) or min_z >= max_z:
            raise ValueError("success.can_world_z requires finite min_m < max_m")
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


def _default_home_arm(side: str) -> np.ndarray:
    joints = LEFT_ARM_JOINTS if side == "left" else RIGHT_ARM_JOINTS
    return np.asarray([DEFAULT_POSE[name] for name in joints], dtype=np.float32)


def _configured_home_arm(value: list[float] | tuple[float, ...] | None, side: str) -> np.ndarray:
    target = _default_home_arm(side) if value is None else np.asarray(value, dtype=np.float32)
    if target.shape != (7,):
        raise ValueError(f"home_poses.{side}_arm must contain 7 joint values, got {target.shape}")
    return target.copy()


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
        home_cfg = self.config.get("home_poses", {})
        if not isinstance(home_cfg, dict):
            raise ValueError("home_poses must be a mapping")
        self.home_targets = {
            "left": _configured_home_arm(home_cfg.get("left_arm"), "left"),
            "right": _configured_home_arm(home_cfg.get("right_arm"), "right"),
        }
        self.home_tolerance = max(float(home_cfg.get("tolerance", 0.03)), 1.0e-4)
        self.phases = self._parse_phases(self.config.get("phases", []))
        if not self.phases:
            raise ValueError(f"No phases configured in {self.config_path}")
        self.phase_index = 0
        self.phase_steps = 0
        self._ik_posture_phase_index: int | None = None
        self._right_tcp_completed_phase_index: int | None = None
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
            require_tcp_reached = bool(raw.get("require_tcp_reached", True))
            left_offset_from_current = raw.get("left_offset_from_current")
            if left_offset_from_current is not None:
                left_offset_from_current = np.asarray(left_offset_from_current, dtype=np.float32)
                if left_offset_from_current.shape != (3,):
                    raise ValueError(
                        f"Phase {raw.get('name')!r} left_offset_from_current must have three values"
                    )
            right_offset_from_current = raw.get("right_offset_from_current")
            if right_offset_from_current is not None:
                right_offset_from_current = np.asarray(right_offset_from_current, dtype=np.float32)
                if right_offset_from_current.shape != (3,):
                    raise ValueError(
                        f"Phase {raw.get('name')!r} right_offset_from_current must have three values"
                    )
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
                    right_home_after_tcp_reached=bool(raw.get("right_home_after_tcp_reached", False)),
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
                    require_tcp_reached=require_tcp_reached,
                    require_left_tcp_reached=bool(
                        raw.get("require_left_tcp_reached", require_tcp_reached)
                    ),
                    require_right_tcp_reached=bool(
                        raw.get("require_right_tcp_reached", require_tcp_reached)
                    ),
                    close_drawer_from_current=bool(raw.get("close_drawer_from_current", False)),
                    drawer_close_target_open_m=max(
                        float(raw.get("drawer_close_target_open_m", 0.0)), 0.0
                    ),
                    drawer_close_overtravel_m=max(
                        float(raw.get("drawer_close_overtravel_m", 0.0)), 0.0
                    ),
                    hold_current_left_pose=bool(raw.get("hold_current_left_pose", False)),
                    left_offset_from_current=left_offset_from_current,
                    right_offset_from_current=right_offset_from_current,
                    target_alpha=(
                        float(np.clip(raw["target_alpha"], 0.001, 1.0))
                        if raw.get("target_alpha") is not None
                        else None
                    ),
                    max_joint_step=(
                        max(float(raw["max_joint_step"]), 1.0e-5)
                        if raw.get("max_joint_step") is not None
                        else None
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

    def _arm_home_error(self, curr_joint_pos: np.ndarray | None, side: str) -> float:
        if curr_joint_pos is None:
            return float("inf")
        ids = np.asarray(self.tcp_controller.isaac_order_joint_ids, dtype=np.int64)
        side_ids = ids[:7] if side == "left" else ids[7:]
        current = np.asarray(curr_joint_pos, dtype=np.float32)
        if current.ndim != 1 or side_ids.size != 7 or int(np.max(side_ids)) >= current.size:
            return float("inf")
        return float(np.max(np.abs(current[side_ids] - self.home_targets[side])))

    def _prepare_current_phase(
        self,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
        drawer_open_m: float | None,
    ) -> None:
        """Resolve relative targets from measured phase-entry TCP poses."""
        phase = self.current_phase
        left_pos = left_quat = None
        if left_pose_base is not None:
            left_pos = np.asarray(left_pose_base[0], dtype=np.float32)
            left_quat = np.asarray(left_pose_base[1], dtype=np.float32)
            if left_pos.shape != (3,) or left_quat.shape != (4,):
                left_pos = left_quat = None
        right_pos = right_quat = None
        if right_pose_base is not None:
            right_pos = np.asarray(right_pose_base[0], dtype=np.float32)
            right_quat = np.asarray(right_pose_base[1], dtype=np.float32)
            if right_pos.shape != (3,) or right_quat.shape != (4,):
                right_pos = right_quat = None

        updated_phase = phase
        if phase.close_drawer_from_current:
            if left_pos is None or left_quat is None:
                raise RuntimeError("Dynamic drawer-close target requires a live left TCP pose")
            closed_anchor = self.anchors.get("drawer_handle_closed")
            open_anchor = self.anchors.get("drawer_handle_open")
            if closed_anchor is None or open_anchor is None or drawer_open_m is None:
                raise RuntimeError("Dynamic drawer-close target requires drawer anchors and live opening")
            close_vector = np.asarray(closed_anchor[0], dtype=np.float32) - np.asarray(
                open_anchor[0], dtype=np.float32
            )
            norm = float(np.linalg.norm(close_vector))
            if norm < 1.0e-6:
                raise RuntimeError("Drawer open and closed anchors do not define a closing direction")
            close_direction = close_vector / norm
            travel = (
                max(float(drawer_open_m) - phase.drawer_close_target_open_m, 0.0)
                + phase.drawer_close_overtravel_m
            )
            target_pos = left_pos + close_direction * travel
            orientation_weight = updated_phase.left.orientation_weight if updated_phase.left is not None else 1.0
            dynamic_target = TcpTarget(target_pos, left_quat.copy(), orientation_weight)
            updated_phase = replace(updated_phase, left=dynamic_target)
        elif phase.hold_current_left_pose:
            if left_pos is None or left_quat is None:
                raise RuntimeError("hold_current_left_pose requires a live left TCP pose")
            orientation_weight = updated_phase.left.orientation_weight if updated_phase.left is not None else 1.0
            dynamic_target = TcpTarget(left_pos.copy(), left_quat.copy(), orientation_weight)
            updated_phase = replace(updated_phase, left=dynamic_target)
        elif phase.left_offset_from_current is not None:
            if left_pos is None or left_quat is None:
                raise RuntimeError("left_offset_from_current requires a live left TCP pose")
            orientation_weight = updated_phase.left.orientation_weight if updated_phase.left is not None else 1.0
            target_quat = (
                updated_phase.left.quat_wxyz.copy() if updated_phase.left is not None else left_quat.copy()
            )
            dynamic_target = TcpTarget(
                left_pos + phase.left_offset_from_current,
                target_quat,
                orientation_weight,
            )
            updated_phase = replace(updated_phase, left=dynamic_target)

        if phase.right_offset_from_current is not None:
            if right_pos is None or right_quat is None:
                raise RuntimeError("right_offset_from_current requires a live right TCP pose")
            orientation_weight = updated_phase.right.orientation_weight if updated_phase.right is not None else 1.0
            dynamic_target = TcpTarget(
                right_pos + phase.right_offset_from_current,
                right_quat.copy(),
                orientation_weight,
            )
            updated_phase = replace(updated_phase, right=dynamic_target)

        self.phases[self.phase_index] = updated_phase

    def tcp_error_metrics(
        self,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
    ) -> dict[str, float]:
        """Return only the four TCP errors used by the collection dashboard."""
        phase = self.current_phase

        def errors(
            pose: tuple[np.ndarray, np.ndarray] | None,
            target: TcpTarget | None,
        ) -> tuple[float, float]:
            if target is None:
                return 0.0, 0.0
            if pose is None:
                return float("nan"), float("nan")
            return _pose_dist(pose, target), _pose_angle(pose, target)

        left_pos, left_rot = errors(left_pose_base, phase.left)
        right_target = (
            None
            if phase.right_home_after_tcp_reached
            and self._right_tcp_completed_phase_index == self.phase_index
            else phase.right
        )
        right_pos, right_rot = errors(right_pose_base, right_target)
        return {
            "left_pos": left_pos,
            "left_rot": left_rot,
            "right_pos": right_pos,
            "right_rot": right_rot,
        }

    def _advance_if_ready(
        self,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
        drawer_open_m: float | None = None,
        curr_joint_pos: np.ndarray | None = None,
    ) -> bool:
        phase = self.current_phase
        left_dist = _pose_dist(left_pose_base, phase.left)
        right_dist = _pose_dist(right_pose_base, phase.right)
        left_angle = _pose_angle(left_pose_base, phase.left)
        right_angle = _pose_angle(right_pose_base, phase.right)
        controlled_errors = []
        if phase.require_left_tcp_reached and phase.left is not None:
            controlled_errors.append((left_dist, left_angle))
        right_tcp_completed = (
            phase.right_home_after_tcp_reached
            and self._right_tcp_completed_phase_index == self.phase_index
        )
        if phase.require_right_tcp_reached and phase.right is not None and not right_tcp_completed:
            controlled_errors.append((right_dist, right_angle))
        reached = not controlled_errors or all(
            dist <= phase.tolerance and angle <= phase.orientation_tolerance
            for dist, angle in controlled_errors
        )
        if phase.drawer_open_min is not None:
            reached = reached and drawer_open_m is not None and drawer_open_m >= phase.drawer_open_min
        if phase.drawer_open_max is not None:
            reached = reached and drawer_open_m is not None and drawer_open_m <= phase.drawer_open_max
        left_home_error = self._arm_home_error(curr_joint_pos, "left") if phase.left_arm_home else 0.0
        right_home_error = self._arm_home_error(curr_joint_pos, "right") if phase.right_arm_home else 0.0
        if phase.left_arm_home:
            reached = reached and left_home_error <= self.home_tolerance
        if phase.right_arm_home:
            reached = reached and right_home_error <= self.home_tolerance
        timed_out = self.phase_steps >= phase.max_steps
        required_steps = max(phase.min_steps, int(np.ceil(phase.hold_seconds / max(self._dt, 1.0e-6))))
        min_wait_done = self.phase_steps >= required_steps
        if not min_wait_done:
            return False
        if not reached and not timed_out:
            return False
        if timed_out and not reached:
            def position_delta(
                pose: tuple[np.ndarray, np.ndarray] | None,
                target: TcpTarget | None,
            ) -> np.ndarray:
                if pose is None or target is None:
                    return np.full(3, np.nan, dtype=np.float32)
                return target.pos - np.asarray(pose[0], dtype=np.float32)

            left_dxyz = position_delta(left_pose_base, phase.left)
            right_dxyz = position_delta(right_pose_base, phase.right)
            self.failed = True
            self.done = True
            self.failure_reason = (
                f"phase={phase.name} timed out after {self.phase_steps} steps "
                f"left_dist={left_dist:.3f} right_dist={right_dist:.3f} "
                f"left_dxyz=({left_dxyz[0]:+.3f},{left_dxyz[1]:+.3f},{left_dxyz[2]:+.3f}) "
                f"right_dxyz=({right_dxyz[0]:+.3f},{right_dxyz[1]:+.3f},{right_dxyz[2]:+.3f}) "
                f"left_angle={left_angle:.3f} right_angle={right_angle:.3f} "
                f"position_tolerance={phase.tolerance:.3f} "
                f"orientation_tolerance={phase.orientation_tolerance:.3f}"
                f" drawer_open={float(drawer_open_m) if drawer_open_m is not None else float('nan'):.3f}"
                f" left_home_error={left_home_error:.3f} right_home_error={right_home_error:.3f}"
                f" require_left_tcp_reached={phase.require_left_tcp_reached}"
                f" require_right_tcp_reached={phase.require_right_tcp_reached}"
            )
            return True
        self.phase_index += 1
        self.phase_steps = 0
        if self.phase_index >= len(self.phases):
            self.done = True
            self.phase_index = len(self.phases) - 1
        else:
            self._prepare_current_phase(left_pose_base, right_pose_base, drawer_open_m)
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
        phase = self.current_phase
        if (
            phase.right_home_after_tcp_reached
            and phase.right is not None
            and self._right_tcp_completed_phase_index != self.phase_index
            and _pose_dist(right_pose_base, phase.right) <= phase.tolerance
            and _pose_angle(right_pose_base, phase.right) <= phase.orientation_tolerance
        ):
            self._right_tcp_completed_phase_index = self.phase_index
        self._advance_if_ready(left_pose_base, right_pose_base, drawer_open_m, curr_joint_pos)
        if self.done:
            return self.action.copy(), self.current_phase.name, self.current_phase.task, True
        phase = self.current_phase

        left_goal = phase.left.as_payload() if phase.left is not None else None
        right_home_active = phase.right_arm_home or (
            phase.right_home_after_tcp_reached
            and self._right_tcp_completed_phase_index == self.phase_index
        )
        right_goal = (
            phase.right.as_payload()
            if phase.right is not None and not right_home_active
            else None
        )
        if left_goal is not None or right_goal is not None:
            if self._ik_posture_phase_index != self.phase_index:
                self.tcp_controller.set_posture_reference(curr_joint_pos)
                self._ik_posture_phase_index = self.phase_index
            arm_targets = self.tcp_controller.compute(curr_joint_pos, dt, left_goal, right_goal)
            self.action[ACTION_SLICES.left_arm] = arm_targets[: len(LEFT_ARM_JOINTS)]
            self.action[ACTION_SLICES.right_arm] = arm_targets[len(LEFT_ARM_JOINTS) :]
        if phase.left_arm_home:
            self.action[ACTION_SLICES.left_arm] = self.home_targets["left"]
        if right_home_active:
            self.action[ACTION_SLICES.right_arm] = self.home_targets["right"]
        if phase.left_hand is not None:
            self.action[ACTION_SLICES.left_hand] = phase.left_hand
        if phase.right_hand is not None:
            self.action[ACTION_SLICES.right_hand] = phase.right_hand

        self.phase_steps += 1
        return self.action.copy(), phase.name, phase.task, False
