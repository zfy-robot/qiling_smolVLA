ARG ROS_BASE_IMAGE=ros:humble-ros-base-jammy@sha256:1813d3c85d7f96ff7d3012d865204583255740182db5d0065f8f8cd029a83138
FROM ${ROS_BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    S4_HW_TELEOP_RUNTIME=system \
    S4_HW_TELEOP_SYSTEM_PYTHON=/usr/bin/python3 \
    S4_HW_TELEOP_SITE_PACKAGES=/opt/s4/hardware_python \
    HW_TELEOP_QI_INSTALL=/opt/s4/qi_ws/install/setup.bash \
    RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       iproute2 libusb-1.0-0 python3-pip python3-colcon-common-extensions \
       ros-humble-pinocchio ros-humble-rmw-cyclonedds-cpp \
       ros-humble-rosidl-default-generators ros-humble-sensor-msgs tini udev usbutils \
    && rm -rf /var/lib/apt/lists/*

COPY docker/robot/requirements.txt /tmp/robot-requirements.txt
RUN python3 -m pip install \
      --index-url "${PIP_INDEX_URL}" \
      --target /opt/s4/hardware_python \
      -r /tmp/robot-requirements.txt

COPY s4_smolvla_isaaclab/hardware_teleop/ros_ws/src /opt/s4/qi_ws/src
RUN source /opt/ros/humble/setup.bash \
    && cd /opt/s4/qi_ws \
    && colcon build --packages-select qi --merge-install

# Keep these after dependency installation so runtime hardening changes do not
# invalidate the expensive apt/pip layers during release verification.
ENV S4_HW_TELEOP_RUNTIME_RESOLVED=system \
    PYTHONNOUSERSITE=1 \
    PYTHONPATH=/opt/s4/hardware_python

COPY docker/common/runtime-entrypoint.sh /usr/local/bin/s4-entrypoint-base
COPY docker/robot/verify_runtime.sh /usr/local/bin/s4-verify-robot
RUN printf '%s\n' \
      '#!/usr/bin/env bash' \
      'set -eo pipefail' \
      '# ROS Humble setup scripts probe optional variables and are not nounset-safe.' \
      'set +u' \
      'source /opt/ros/humble/setup.bash' \
      'source /opt/s4/qi_ws/install/setup.bash' \
      'exec /usr/local/bin/s4-entrypoint-base "$@"' \
      > /usr/local/bin/s4-robot-entrypoint \
    && chmod 0755 /usr/local/bin/s4-entrypoint-base /usr/local/bin/s4-robot-entrypoint \
       /usr/local/bin/s4-verify-robot

WORKDIR /workspace/smolVLA/s4_smolvla_isaaclab
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/s4-robot-entrypoint"]
CMD ["bash"]
