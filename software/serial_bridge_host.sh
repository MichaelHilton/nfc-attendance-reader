#!/usr/bin/env bash
# Run this ON THE HOST (the Mac/PC the reader is plugged into), NOT in the
# container. It exposes the board's USB serial port over TCP so the dev
# container can reach it. See software/SERIAL_BRIDGE.md.
#
#   ./serial_bridge_host.sh                     # auto-detect port, TCP 9600
#   ./serial_bridge_host.sh /dev/cu.usbserial-XXXX
#   ./serial_bridge_host.sh /dev/cu.usbserial-XXXX 115200 9600
#
# Requires socat:  macOS -> brew install socat   |   Debian/Ubuntu -> apt install socat
set -euo pipefail

PORT="${1:-}"
BAUD="${2:-115200}"
TCP_PORT="${3:-9600}"

if [[ -z "$PORT" ]]; then
	# Grab the first likely USB-serial device (macOS cu.* first, then Linux).
	PORT=$(ls /dev/cu.usbserial-* /dev/cu.usbmodem* /dev/cu.wchusbserial* \
	          /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n1 || true)
fi

if [[ -z "$PORT" || ! -e "$PORT" ]]; then
	echo "No serial port found. Plug the board in, or pass one explicitly:" >&2
	echo "  $0 /dev/cu.usbserial-XXXX" >&2
	exit 1
fi

command -v socat >/dev/null || { echo "socat not installed (brew install socat / apt install socat)" >&2; exit 1; }

echo "Bridging $PORT @ ${BAUD} baud  <-->  TCP *:${TCP_PORT}"
echo "Leave this running. Ctrl-C to stop. Opening the port resets the ESP32 once."
exec socat -d -d \
	TCP-LISTEN:"${TCP_PORT}",reuseaddr,fork \
	FILE:"${PORT}",b"${BAUD}",raw,echo=0,crtscts=0
