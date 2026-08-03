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

    def as_payload(self) -> dict[str, list[float]]:
        return {
            "pos": [float(x) for x in self.pos],
            "quat_wxyz": [float(x) for x in self.quat_wxyz],
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
    max_steps: int
    tolerance: float


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except Exception as exc:  # pragma: no cover - depends on env packaging
        raise RuntimeError("PyYAML is required for drawer scripted task config") from exc
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Drawer scripted config must be a mapping: {path}")
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


def _tcp_target(raw: dict[str, Any] | None, default_tolerance: float) -> TcpTarget | None:
    del default_tolerance
    if raw is None:
        return None
    pos = np.asarray(raw["pos"], dtype=np.float32)
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
    return TcpTarget(pos=pos, quat_wxyz=quat.astype(np.float32))


def _home_arm(side: str) -> np.ndarray:
    joints = LEFT_ARM_JOINTS if side == "left" else RIGHT_ARM_JOINTS
    return np.asarray([DEFAULT_POSE[name] for name in joints], dtype=np.float32)


def _pose_dist(current_pose: tuple[np.ndarray, np.ndarray] | None, target: TcpTarget | None) -> float:
    if current_pose is None or target is None:
        return 0.0
    return float(np.linalg.norm(np.asarray(current_pose[0], dtype=np.float32) - target.pos))


class DrawerInsertCloseController:
    """Scripted drawer task controller using independent left/right arm and hand targets."""

    def __init__(
        self,
        tcp_controller,
        config_path: Path = DEFAULT_SCRIPTED_CONFIG,
        *,
        initial_action: np.ndarray | None = None,
    ):
        self.tcp_controller = tcp_controller
        self.config_path = Path(config_path)
        self.config = _load_yaml(self.config_path)
        controller_cfg = self.config.get("controller", {})
        self.default_tolerance = float(controller_cfg.get("default_tolerance", 0.035))
        self.global_task = str(controller_cfg.get("task", "Open the drawer, place the object inside, and close the drawer."))
        self.phases = self._parse_phases(self.config.get("phases", []))
        if not self.phases:
            raise ValueError(f"No phases configured in {self.config_path}")
        self.phase_index = 0
        self.phase_steps = 0
        self.done = False
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
            phases.append(
                DrawerPhase(
                    name=str(raw["name"]),
                    task=str(raw.get("task", self.global_task)),
                    left=_tcp_target(raw.get("left"), tolerance),
                    right=_tcp_target(raw.get("right"), tolerance),
                    left_hand=_hand_target(raw.get("left_hand"), "left"),
                    right_hand=_hand_target(raw.get("right_hand"), "right"),
                    left_arm_home=bool(raw.get("left_arm_home", False)),
                    right_arm_home=bool(raw.get("right_arm_home", False)),
                    min_steps=max(int(raw.get("min_steps", 0)), 0),
                    max_steps=max(int(raw.get("max_steps", 240)), 1),
                    tolerance=max(tolerance, 0.001),
                )
            )
        return phases

    @property
    def current_phase(self) -> DrawerPhase:
        return self.phases[min(self.phase_index, len(self.phases) - 1)]

    @property
    def current_task(self) -> str:
        return self.current_phase.task

    def _advance_if_ready(
        self,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
    ) -> bool:
        phase = self.current_phase
        left_dist = _pose_dist(left_pose_base, phase.left)
        right_dist = _pose_dist(right_pose_base, phase.right)
        controlled_dists = []
        if phase.left is not None:
            controlled_dists.append(left_dist)
        if phase.right is not None:
            controlled_dists.append(right_dist)
        reached = not controlled_dists or max(controlled_dists) <= phase.tolerance
        timed_out = self.phase_steps >= phase.max_steps
        min_wait_done = self.phase_steps >= phase.min_steps
        if not min_wait_done:
            return False
        if not reached and not timed_out:
            return False
        old_name = phase.name
        self.phase_index += 1
        self.phase_steps = 0
        if self.phase_index >= len(self.phases):
            self.done = True
            self.phase_index = len(self.phases) - 1
        print(
            f"[DRAWER] phase {old_name} -> {self.current_phase.name if not self.done else 'done'} "
            f"left_dist={left_dist:.3f} right_dist={right_dist:.3f} reached={reached} timeout={timed_out}",
            flush=True,
        )
        return True

    def step(
        self,
        curr_joint_pos: np.ndarray,
        dt: float,
        left_pose_base: tuple[np.ndarray, np.ndarray] | None,
        right_pose_base: tuple[np.ndarray, np.ndarray] | None,
    ) -> tuple[np.ndarray, str, str, bool]:
        if self.done:
            return self.action.copy(), self.current_phase.name, self.current_phase.task, True
        self._advance_if_ready(left_pose_base, right_pose_base)
        phase = self.current_phase

        left_goal = phase.left.as_payload() if phase.left is not None else None
        right_goal = phase.right.as_payload() if phase.right is not None else None
        if left_goal is not None or right_goal is not None:
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
