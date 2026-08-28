#!/usr/bin/env bash
# Run this INSIDE the dev container. It connects to the host's serial_bridge_host.sh
# over TCP and exposes a local PTY you can point the Python tools at:
#
#   ./serial_bridge.sh &                       # creates ./reader-port -> /dev/pts/N
#   python3 sd_download.py --port ./reader-port
#   python3 sd_upload.py roster.csv --port ./reader-port
#
#   ./serial_bridge.sh host.docker.internal 9600 ./reader-port
#
# Auto-detect (find_port) will NOT see this PTY, so always pass --port.
set -euo pipefail

HOST="${1:-host.docker.internal}"
TCP_PORT="${2:-9600}"
LINK="${3:-$(dirname "$0")/reader-port}"

command -v socat >/dev/null || { echo "socat missing; rebuild the container or: sudo apt-get install -y socat" >&2; exit 1; }

echo "Linking ${LINK}  <-->  ${HOST}:${TCP_PORT}"
echo "Point the tools at:  --port ${LINK}"
exec socat -d -d \
	PTY,link="${LINK}",raw,echo=0,mode=666 \
	TCP:"${HOST}":"${TCP_PORT}"
