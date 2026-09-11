ARG CUDA_BASE_IMAGE=nvidia/cuda:12.8.1-base-ubuntu22.04@sha256:001469ea0f3dec85a1ca929aeea3b58ae369d4c11228b10aec1f642bb6ca7a6f
FROM ${CUDA_BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PATH=/opt/conda/bin:${PATH} \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    OMNI_KIT_ACCEPT_EULA=Y \
    NVIDIA_DRIVER_CAPABILITIES=graphics,compute,utility \
    VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd_headless.json \
    S4_ISAACLAB_ENV=env_isaaclab \
    S4_SMOLVLA_ENV=smolvla \
    S4_ISAAC_ENV_HELPER=/usr/local/lib/s4/isaac_env.sh \
    S4_ROLLOUT_CHECKPOINT=/artifacts/policies/sim/drawer_insert_close_v4/350000/pretrained_model

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates cmake curl ffmpeg git libegl1 libgl1 \
       libglib2.0-0 libglu1-mesa libsm6 libvulkan1 libxext6 libxrandr2 \
       libxrender1 libxt6 libxtst6 pkg-config rsync tini unzip vulkan-tools zstd \
    && rm -rf /var/lib/apt/lists/*

COPY docker/vendor/Miniforge3-25.3.1-0-Linux-x86_64.sh /tmp/Miniforge3-25.3.1-0-Linux-x86_64.sh
COPY docker/common/install_miniforge.sh /tmp/install-miniforge
RUN bash /tmp/install-miniforge && rm -f /tmp/install-miniforge

COPY docker/sim/conda-environment.yml /tmp/isaaclab.yml
COPY docker/sim/requirements.txt /tmp/isaaclab-requirements.txt
COPY docker/pip-build-constraints.txt /tmp/isaaclab-pip-build-constraints.txt
RUN conda env create -f /tmp/isaaclab.yml
RUN --mount=type=cache,target=/root/.cache/pip \
    conda run --no-capture-output -n env_isaaclab python -m pip install --upgrade pip \
       --index-url "${PIP_INDEX_URL}" \
    && conda run --no-capture-output -n env_isaaclab python -m pip install \
       --index-url "${PIP_INDEX_URL}" -r /tmp/isaaclab-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    conda run --no-capture-output -n env_isaaclab python -m pip install \
       --index-url "${PIP_INDEX_URL}" \
       --extra-index-url https://pypi.nvidia.com \
       'isaacsim[all,extscache]==5.1.0'
RUN --mount=type=cache,target=/root/.cache/pip \
    conda run --no-capture-output -n env_isaaclab python -m pip install \
       --index-url "${PIP_INDEX_URL}" 'setuptools<81' 'torchaudio==2.7.0' \
    && conda run --no-capture-output -n env_isaaclab bash -lc \
       'export PIP_BUILD_CONSTRAINT=/tmp/isaaclab-pip-build-constraints.txt; python -m pip install flatdict==4.0.1' \
    && conda clean -a -y

# The current simulation rollout launches the policy worker as a subprocess.
# Keep the policy environment in the sim image for the compatibility release;
# the standalone policy image remains the training and real-robot inference image.
COPY docker/policy/conda-environment.yml /tmp/policy.yml
COPY docker/policy/requirements.txt /tmp/policy-requirements.txt
RUN conda env create -f /tmp/policy.yml
RUN --mount=type=cache,target=/root/.cache/pip \
    conda run --no-capture-output -n smolvla python -m pip install \
       --index-url "${PIP_INDEX_URL}" -r /tmp/policy-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    conda run --no-capture-output -n smolvla python -m pip install --index-url https://download.pytorch.org/whl/cu128 \
       'torch==2.7.0+cu128' 'torchvision==0.22.0+cu128' 'torchaudio==2.7.0' \
    && conda clean -a -y

COPY IsaacLab /opt/src/IsaacLab
RUN touch /run/.containerenv \
    && conda run --no-capture-output -n env_isaaclab bash -lc \
       'export PIP_BUILD_CONSTRAINT=/tmp/isaaclab-pip-build-constraints.txt; cd /opt/src/IsaacLab; ./isaaclab.sh --install none' \
    && rm -f /run/.containerenv

COPY lerobot /opt/src/lerobot
RUN conda run --no-capture-output -n smolvla python -m pip install /opt/src/lerobot \
    && conda run --no-capture-output -n smolvla python -m pip check

COPY docker/vulkan/nvidia_icd_headless.json /etc/vulkan/icd.d/nvidia_icd_headless.json
COPY docker/isaac_env.sh /usr/local/lib/s4/isaac_env.sh
COPY docker/common/runtime-entrypoint.sh /usr/local/bin/s4-entrypoint
RUN chmod 0755 /usr/local/lib/s4/isaac_env.sh /usr/local/bin/s4-entrypoint \
    && conda run -n env_isaaclab python -c "import importlib.metadata as m; assert m.version('isaacsim') == '5.1.0.0'; import isaaclab" \
    && conda run -n smolvla python -c "import torch, lerobot; assert torch.version.cuda == '12.8'"

WORKDIR /workspace/smolVLA/s4_smolvla_isaaclab
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/s4-entrypoint"]
CMD ["bash"]
