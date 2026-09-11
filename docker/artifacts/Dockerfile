ARG ARTIFACT_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${ARTIFACT_BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_DEFAULT_TIMEOUT=300
ARG PIP_RETRIES=10
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1
RUN python3 -m pip install \
      --index-url "${PIP_INDEX_URL}" \
      --timeout "${PIP_DEFAULT_TIMEOUT}" \
      --retries "${PIP_RETRIES}" \
      'modelscope==1.39.1' \
      'pyyaml==6.0.2'

WORKDIR /workspace/smolVLA
ENTRYPOINT ["python3", "scripts/release/pull_modelscope_artifacts.py"]
