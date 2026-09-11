#!/usr/bin/env bash
set -euo pipefail

version="25.3.1-0"
sha256="376b160ed8130820db0ab0f3826ac1fc85923647f75c1b8231166e3d559ab768"
installer="/tmp/Miniforge3-${version}-Linux-x86_64.sh"

[[ -f "$installer" ]] || {
    echo "Missing build input: $installer" >&2
    exit 1
}
echo "$sha256  $installer" | sha256sum -c -
bash "$installer" -b -p /opt/conda
rm -f "$installer"
/opt/conda/bin/conda config --system --set channel_priority strict
/opt/conda/bin/conda config --system --set remote_connect_timeout_secs 30
/opt/conda/bin/conda config --system --set remote_read_timeout_secs 300
/opt/conda/bin/conda config --system --set remote_max_retries 10
/opt/conda/bin/conda clean -a -y
