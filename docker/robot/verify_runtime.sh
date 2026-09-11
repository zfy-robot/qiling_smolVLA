#!/usr/bin/env bash
set -euo pipefail

project_root="${S4_PROJECT_ROOT:-/workspace/smolVLA/s4_smolvla_isaaclab}"
qi_setup="${HW_TELEOP_QI_INSTALL:-/opt/s4/qi_ws/install/setup.bash}"
python_bin="${S4_HW_TELEOP_SYSTEM_PYTHON:-/usr/bin/python3}"
export PYTHONPATH="${S4_HW_TELEOP_SITE_PACKAGES:-/opt/s4/hardware_python}:${PYTHONPATH:-}"
export PYTHONNOUSERSITE=1
export S4_HW_TELEOP_RUNTIME_RESOLVED="${S4_HW_TELEOP_RUNTIME_RESOLVED:-${S4_HW_TELEOP_RUNTIME:-system}}"

if [[ ! -f "${qi_setup}" ]]; then
  echo "[FAIL] image-built qi ROS messages are missing: ${qi_setup}" >&2
  exit 1
fi
if [[ ! -f "${S4_ROBOT_ASSET_ROOT}/urdf/s4_40dof_merged.urdf" ]]; then
  echo "[FAIL] mounted robot URDF is missing" >&2
  exit 1
fi

cd "${project_root}"
# shellcheck disable=SC1091
source hardware_teleop/scripts/source_ros_env.sh

"${python_bin}" - <<'PY'
import sys
import aiohttp
import cv2
import daqp
import h5py
import msgpack
import numpy
import pinocchio
import pyrealsense2
import qpsolvers
import quadprog
import rclpy
import scipy
import yaml
import zmq
from qi.msg import HandCmd, HandsCmd, LowCmd, LowState, MotorCmd

assert sys.version_info[:2] == (3, 10), sys.version
assert numpy.__version__ == "1.26.4", numpy.__version__
assert scipy.__version__ == "1.15.2", scipy.__version__
assert aiohttp.__version__ == "3.14.3", aiohttp.__version__
assert qpsolvers.__version__ == "4.12.0", qpsolvers.__version__
assert str(pinocchio.__file__).startswith("/opt/ros/humble/"), pinocchio.__file__
print(
    "[OK] robot Python/ROS imports: "
    f"python={sys.version.split()[0]} numpy={numpy.__version__} "
    f"pinocchio={pinocchio.__version__} scipy={scipy.__version__}"
)
print("[OK] qi messages: HandCmd HandsCmd LowCmd LowState MotorCmd")
devices = pyrealsense2.context().query_devices()
print(f"[OK] RealSense read-only enumeration: devices={len(devices)}")
PY

"${python_bin}" -m hardware_teleop.env_check --robot-profile --require-daqp
"${python_bin}" - <<'PY'
from real_vla.config_loader import load_collection_config
from real_vla_stack.common.config import load_pipeline_config

collection = load_collection_config()
pipeline = load_pipeline_config()
assert pipeline.contract.state_dim == pipeline.contract.action_dim == 8
assert len(pipeline.contract.camera_keys) == 2
print(
    "[OK] real configuration: "
    f"task={pipeline.contract.task_id} cameras={pipeline.contract.camera_keys}"
)
assert collection is not None
print("[OK] collection config loaded without opening cameras or robot devices")
PY

echo "[OK] robot no-hardware runtime verification passed (no ROS publishers created)"
