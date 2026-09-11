#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${project_root}"

python3 scripts/ci/validate_repository.py

while IFS= read -r -d '' script; do
  bash -n "${script}"
done < <(
  git ls-files -z '*.sh' s4 \
    ':!IsaacLab/**' ':!lerobot/**' ':!docker/vendor/**'
)
echo "[OK] shell syntax"

docker compose \
  --profile setup --profile sim --profile sim-offline --profile train --profile real \
  config --quiet
echo "[OK] Compose config"

status="$(git submodule status --recursive)"
if grep -Eq '^[+-]' <<<"${status}"; then
  echo "Submodule is missing or differs from the recorded gitlink:" >&2
  echo "${status}" >&2
  exit 1
fi
echo "[OK] initialized submodules match recorded commits"
