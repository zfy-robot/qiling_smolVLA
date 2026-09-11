#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${project_root}"

version="${1:-0.1.0}"
selection="${2:-all}"
namespace="${S4_GHCR_NAMESPACE:-zfy-robot}"
push_attempts="${S4_GHCR_PUSH_ATTEMPTS:-3}"

if [[ ! "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Usage: $0 VERSION [robot|policy|sim|all]" >&2
  exit 2
fi
case "${selection}" in
  robot|policy|sim|all) ;;
  *) echo "Usage: $0 VERSION [robot|policy|sim|all]" >&2; exit 2 ;;
esac
if [[ ! "${push_attempts}" =~ ^[1-9][0-9]*$ ]]; then
  echo "S4_GHCR_PUSH_ATTEMPTS must be a positive integer" >&2
  exit 2
fi

push_with_retry() {
  local remote_ref="$1"
  local attempt

  for ((attempt = 1; attempt <= push_attempts; attempt++)); do
    echo "[GHCR] push attempt ${attempt}/${push_attempts}: ${remote_ref}"
    if docker image push "${remote_ref}"; then
      return 0
    fi
    if ((attempt < push_attempts)); then
      echo "[GHCR] push interrupted; retrying in 15 seconds (uploaded layers are reused)" >&2
      sleep 15
    fi
  done

  echo "[GHCR] push failed after ${push_attempts} attempts: ${remote_ref}" >&2
  return 1
}

publish_one() {
  local service="$1"
  local local_ref="s4-smolvla-${service}:dev"
  local remote_ref="ghcr.io/${namespace}/qiling-smolvla-${service}:v${version}"

  docker image inspect "${local_ref}" >/dev/null
  echo "[GHCR] tagging ${local_ref} -> ${remote_ref}"
  docker image tag "${local_ref}" "${remote_ref}"
  echo "[GHCR] pushing ${remote_ref}"
  push_with_retry "${remote_ref}"
  echo "[GHCR] remote identity"
  docker buildx imagetools inspect "${remote_ref}"
}

if [[ "${selection}" == "all" ]]; then
  # Smallest first: fail early on permissions before uploading multi-GB images.
  for service in robot policy sim; do
    publish_one "${service}"
  done
else
  publish_one "${selection}"
fi
