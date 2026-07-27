#!/usr/bin/env python
"""Future HDF5 recorder entry for S4 bimanual demonstrations.

This is intentionally a scaffold. The current simulator can be tested with
`bash run.sh sim`; once true grasp/place succeeds, this entry should collect
episodes and write the canonical HDF5 schema from `data/hdf5_schema.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s4_pipeline.config import load_project_config


parser = argparse.ArgumentParser(description="Record S4 bimanual demos to BenchHub-compatible HDF5.")
parser.add_argument("--output", type=Path, default=None)
parser.add_argument("--num-episodes", type=int, default=3)
parser.add_argument("--source", choices=["scripted", "keyboard", "vr"], default="scripted")


def main() -> None:
    args = parser.parse_args()
    cfg = load_project_config()
    output = args.output or cfg.dataset.staging_root / "s4_bimanual_red_blue_plate_debug.hdf5"
    raise SystemExit(
        "HDF5 recording scaffold is installed but not implemented yet.\n"
        f"Planned output: {output}\n"
        f"Episodes: {args.num_episodes}, source: {args.source}\n"
        "Finish true grasp/place first, then wire the running IsaacLab scene into "
        "data.dataset_writer.Hdf5DemoWriter."
    )


if __name__ == "__main__":
    main()

