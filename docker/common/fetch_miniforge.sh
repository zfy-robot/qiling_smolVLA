#!/usr/bin/env bash
set -euo pipefail

version="25.3.1-0"
expected_sha256="376b160ed8130820db0ab0f3826ac1fc85923647f75c1b8231166e3d559ab768"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
destination="${1:-${project_root}/docker/vendor/Miniforge3-${version}-Linux-x86_64.sh}"
url="https://github.com/conda-forge/miniforge/releases/download/${version}/Miniforge3-${version}-Linux-x86_64.sh"

mkdir -p "$(dirname "${destination}")"
if [[ -f "${destination}" ]] && echo "${expected_sha256}  ${destination}" | sha256sum --check --quiet -; then
    echo "[MINIFORGE] cached and verified: ${destination}"
    exit 0
fi

echo "[MINIFORGE] downloading with host proxy settings: ${url}"
curl --fail --location --http1.1 --continue-at - \
    --retry 12 --retry-all-errors --retry-delay 5 \
    --connect-timeout 30 --speed-time 120 --speed-limit 1024 \
    --output "${destination}" "${url}"
echo "${expected_sha256}  ${destination}" | sha256sum --check --status - || {
    echo "[MINIFORGE][FAIL] checksum mismatch: ${destination}" >&2
    exit 1
}
echo "[MINIFORGE] downloaded and verified: ${destination}"
