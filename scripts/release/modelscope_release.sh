#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
staging_dir="${repo_root}/release/staging/qiling_smolvla"
state_dir="${repo_root}/.s4/modelscope"
image="${S4_ARTIFACT_IMAGE:-s4-smolvla-artifacts:dev}"
repo_id="${S4_MODELSCOPE_REPO:-zfy2qiling/qiling_smolvla}"
revision="${S4_MODELSCOPE_UPLOAD_REVISION:-master}"
workers="${S4_MODELSCOPE_UPLOAD_WORKERS:-4}"

mkdir -p "${state_dir}/home" "${state_dir}/cache"

docker_options=(
  --rm
  --network host
  -e "MODELSCOPE_HOME=/modelscope/home"
  -e "MODELSCOPE_CACHE=/modelscope/cache"
  -e "MODELSCOPE_API_TIMEOUT=${MODELSCOPE_API_TIMEOUT:-300}"
  -e "MODELSCOPE_API_CONNECT_TIMEOUT=${MODELSCOPE_API_CONNECT_TIMEOUT:-30}"
  -e "MODELSCOPE_API_MAX_RETRIES=${MODELSCOPE_API_MAX_RETRIES:-10}"
  -e "MODELSCOPE_UPLOAD_BLOB_MAX_ATTEMPTS=${MODELSCOPE_UPLOAD_BLOB_MAX_ATTEMPTS:-10}"
  -e "MODELSCOPE_UPLOAD_FAILED_FILE_MAX_RETRY_ROUNDS=${MODELSCOPE_UPLOAD_FAILED_FILE_MAX_RETRY_ROUNDS:-5}"
  -e HTTP_PROXY
  -e HTTPS_PROXY
  -e NO_PROXY
  -e http_proxy
  -e https_proxy
  -e no_proxy
  -v "${state_dir}/home:/modelscope/home"
  -v "${state_dir}/cache:/modelscope/cache"
  --entrypoint modelscope
)

usage() {
  cat <<'EOF'
Usage: scripts/release/modelscope_release.sh <login|logout|check|upload>

  login   Prompt for a ModelScope token and persist it under .s4/ (gitignored).
  logout  Remove the locally persisted ModelScope credentials.
  check   Verify identity, public visibility, staged files, and SHA256 checksums.
  upload  Re-run all checks, then upload the staged tree with resume enabled.
EOF
}

modelscope() {
  docker run "${docker_options[@]}" "${image}" "$@"
}

check_release() {
  if [[ ! -f "${staging_dir}/SHA256SUMS" ]]; then
    echo "Missing staged release: ${staging_dir}" >&2
    echo "Run prepare_modelscope_release.py --materialize first." >&2
    exit 1
  fi

  modelscope whoami

  local repo_info
  repo_info="$(modelscope info "${repo_id}" --repo-type dataset)"
  printf '%s\n' "${repo_info}"
  if ! grep -Eq '^visibility[[:space:]]*:[[:space:]]*public[[:space:]]*$' <<<"${repo_info}"; then
    echo "Refusing upload: ${repo_id} is not public." >&2
    echo "Set the dataset repository visibility to public on ModelScope, then rerun check." >&2
    exit 1
  fi

  echo "Verifying staged artifact checksums..."
  (cd "${staging_dir}" && sha256sum --quiet -c SHA256SUMS)
  echo "Release checks passed."
}

case "${1:-}" in
  login)
    docker run -it "${docker_options[@]}" "${image}" login
    ;;
  logout)
    modelscope logout
    ;;
  check)
    check_release
    ;;
  upload)
    check_release
    docker run "${docker_options[@]}" \
      -v "${staging_dir}:/upload" \
      "${image}" \
      upload "${repo_id}" /upload \
      --repo-type dataset \
      --revision "${revision}" \
      --commit-message "Publish S4 smolVLA tutorial artifacts" \
      --commit-description "Public release: base models, simulation and real datasets, simulation policy at 350k, real policy at 300k, and project robot/scene assets." \
      --max-workers "${workers}" \
      --use-cache
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
