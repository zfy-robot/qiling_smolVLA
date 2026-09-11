ARG CUDA_BASE_IMAGE=nvidia/cuda:12.8.1-base-ubuntu22.04@sha256:001469ea0f3dec85a1ca929aeea3b58ae369d4c11228b10aec1f642bb6ca7a6f
FROM ${CUDA_BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PATH=/opt/conda/bin:${PATH} \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    S4_SMOLVLA_PYTHON=/opt/conda/envs/smolvla/bin/python

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl ffmpeg git tini \
    && rm -rf /var/lib/apt/lists/*

COPY docker/vendor/Miniforge3-25.3.1-0-Linux-x86_64.sh /tmp/Miniforge3-25.3.1-0-Linux-x86_64.sh
COPY docker/common/install_miniforge.sh /tmp/install-miniforge
RUN bash /tmp/install-miniforge && rm -f /tmp/install-miniforge

COPY docker/policy/conda-environment.yml /tmp/environment.yml
COPY docker/policy/requirements.txt /tmp/requirements.txt
RUN conda env create -f /tmp/environment.yml
RUN --mount=type=cache,target=/root/.cache/pip \
    conda run --no-capture-output -n smolvla python -m pip install \
       --index-url "${PIP_INDEX_URL}" -r /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    conda run --no-capture-output -n smolvla python -m pip install --index-url https://download.pytorch.org/whl/cu128 \
       'torch==2.7.0+cu128' 'torchvision==0.22.0+cu128' 'torchaudio==2.7.0' \
    && conda clean -a -y

COPY lerobot /opt/src/lerobot
RUN conda run --no-capture-output -n smolvla python -m pip install /opt/src/lerobot \
    && rm -rf /opt/src/lerobot \
    && conda run --no-capture-output -n smolvla python -m pip check

COPY docker/common/runtime-entrypoint.sh /usr/local/bin/s4-entrypoint
RUN chmod 0755 /usr/local/bin/s4-entrypoint

WORKDIR /workspace/smolVLA/s4_smolvla_isaaclab
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/s4-entrypoint"]
CMD ["bash"]
