#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
bash 12_collect_convert_train.sh "$@"
