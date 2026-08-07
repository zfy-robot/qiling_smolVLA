#!/usr/bin/env python3
"""Inspect local S4 pipeline config without launching Isaac Sim."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.config import load_project_config
from s4_pipeline.paths import REFERENCE_LEROBOT_DIR, SMOLVLA_CONFIG_PATH
from s4_robot.control_mapping import BIMANUAL_ACTION_DIM, format_action_layout
from tasks import TASK_REGISTRY, get_task_spec


def main() -> None:
    cfg = load_project_config()
    task = get_task_spec(cfg.dataset.task_id)
    print("S4 local pipeline")
    print(f"  active task id:  {cfg.dataset.task_id}")
    print(f"  active task:     {task.name}")
    print(f"  task module:     scene={task.scene_builder} controller={task.scripted_controller}")
    print(f"  dataset repo_id: {cfg.dataset.repo_id}")
    print(f"  staging root:    {cfg.dataset.staging_root}")
    print(f"  lerobot root:    {cfg.dataset.lerobot_root}")
    print(f"  scene usd:       {cfg.scene.scene_usd}")
    print(f"  table usd:       {cfg.scene.table_usd}")
    print(f"  table top z:     {cfg.scene.table_top_z}")
    print(f"  feature state:   {cfg.features.state_dim}")
    print(f"  active state:    {cfg.features.active_state_dim}")
    print(f"  feature action:  {cfg.features.action_dim}")
    print(f"  action dim code: {BIMANUAL_ACTION_DIM}")
    print(f"  smolvla config:  {SMOLVLA_CONFIG_PATH}")
    print(f"  reference lerobot exists:  {REFERENCE_LEROBOT_DIR.exists()}")
    print()
    print("Registered tasks:")
    for task_id, spec in sorted(TASK_REGISTRY.items()):
        marker = "*" if task_id == cfg.dataset.task_id else " "
        print(f" {marker} {task_id}: {spec.description}")
    print()
    print(format_action_layout())


if __name__ == "__main__":
    main()
