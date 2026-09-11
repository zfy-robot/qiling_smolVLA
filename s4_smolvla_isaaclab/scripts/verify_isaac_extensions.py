#!/usr/bin/env python3
"""Resolve the locked URDF importer without constructing the task scene."""

from __future__ import annotations

import argparse
import os
import sys
import traceback

from isaaclab.app import AppLauncher


parser = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
simulation_app = AppLauncher(args).app


def main() -> int:
    import omni.kit.app

    manager = omni.kit.app.get_app().get_extension_manager()
    extension_id = "isaacsim.asset.importer.urdf-2.4.31"
    manager.set_extension_enabled_immediate(extension_id, True)
    if not manager.is_extension_enabled(extension_id):
        raise RuntimeError(f"Kit did not enable {extension_id}")
    from isaacsim.asset.importer.urdf._urdf import acquire_urdf_interface

    if acquire_urdf_interface() is None:
        raise RuntimeError("URDF importer interface is unavailable")
    print("[OK] offline Kit extension resolved: isaacsim.asset.importer.urdf 2.4.31", flush=True)
    print("[OK] offline Kit dependency resolved: omni.kit.pip_archive", flush=True)
    return 0


if __name__ == "__main__":
    try:
        result = main()
    except BaseException:
        traceback.print_exc()
        result = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(result)
