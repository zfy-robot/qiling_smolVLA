#!/usr/bin/env python3
"""List registered task modules and their config files."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks import TASK_REGISTRY


def main() -> None:
    print("Registered S4 task modules:")
    for task_id, spec in sorted(TASK_REGISTRY.items()):
        print(f"\n{task_id}")
        print(f"  name:        {spec.name}")
        print(f"  description: {spec.description}")
        print(f"  dataset cfg: {spec.dataset_config}")
        print(f"  train cfg:   {spec.train_config}")
        print(f"  data:        mode={spec.data.control_mode} state={spec.data.state_dim} action={spec.data.action_dim}")
        print(f"  scene:       {spec.scene_builder}")
        print(f"  controller:  {spec.scripted_controller}")
        for note in spec.notes:
            print(f"  note:        {note}")


if __name__ == "__main__":
    main()
