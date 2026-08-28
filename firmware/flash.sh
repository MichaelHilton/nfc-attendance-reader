#!/usr/bin/env bash
# Compile + flash the attendance-reader firmware to the CYD with arduino-cli.
#
# Run this ON THE HOST the board is plugged into. USB flashing does NOT work
# through software/serial_bridge.sh (esptool needs the raw USB device), and the
# devcontainer has no access to the host USB port -- inside the container only the
# compile check (-n) works. Use the CYD's micro-USB port (left edge) for
# programming, NOT the battery module's USB-C.
#
#   ./flash.sh                              # auto-detect port, compile + upload
#   ./flash.sh /dev/cu.usbserial-XXXX       # explicit port
#   ./flash.sh -n                           # compile only, don't upload
#   ./flash.sh /dev/ttyUSB0 115200          # explicit port + upload speed
#
# One-time setup (the devcontainer does this for you on create):
#   ./firmware/setup-arduino.sh
#   TFT_eSPI also needs a User_Setup.h for the 3.5" ST7796 CYD (see DESIGN_NOTES.md).
set -euo pipefail

# setup-arduino.sh drops arduino-cli here; it is not on macOS's default PATH.
export PATH="$HOME/.local/bin:$PATH"

FQBN="esp32:esp32:esp32"
SKETCH_DIR="$(cd "$(dirname "$0")" && pwd)/attendance_reader_PN532"

COMPILE_ONLY=0
if [[ "${1:-}" == "-n" || "${1:-}" == "--compile-only" ]]; then
	COMPILE_ONLY=1; shift
fi

PORT="${1:-}"
BAUD="${2:-115200}"   # CH340 on the CYD is unreliable above 115200

command -v arduino-cli >/dev/null || {
	echo "arduino-cli not found -- run:  ./firmware/setup-arduino.sh" >&2
	exit 1
}

arduino-cli core list 2>/dev/null | grep -q '^esp32:esp32' || {
	echo "esp32 core / libraries not installed -- run:  ./firmware/setup-arduino.sh" >&2
	exit 1
}

[[ -f "$SKETCH_DIR/attendance_reader_PN532.ino" ]] || {
	echo "Sketch not found at $SKETCH_DIR" >&2; exit 1
}

for f in wifi_config.h secret_key.h; do
	[[ -f "$SKETCH_DIR/$f" ]] || \
		echo "WARNING: $SKETCH_DIR/$f missing -- building with placeholders" \
		     "(no real WiFi / roster tokens won't match)." >&2
done

echo "==> Compiling ($FQBN)"
arduino-cli compile --fqbn "$FQBN" "$SKETCH_DIR"

if [[ "$COMPILE_ONLY" == 1 ]]; then
	echo "Compile OK (--compile-only, not uploading)."
	exit 0
fi

if [[ -z "$PORT" ]]; then
	# First likely USB-serial device (macOS cu.* first, then Linux).
	PORT=$(ls /dev/cu.usbserial-* /dev/cu.usbmodem* /dev/cu.wchusbserial* \
	          /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -n1 || true)
fi
if [[ -z "$PORT" || ! -e "$PORT" ]]; then
	echo "No serial port found. Plug the board into its micro-USB port, or pass one:" >&2
	echo "  $0 /dev/cu.usbserial-XXXX" >&2
	exit 1
fi

echo "==> Uploading to $PORT @ ${BAUD} baud"
arduino-cli upload --fqbn "$FQBN" -p "$PORT" \
	--upload-property upload.speed="$BAUD" "$SKETCH_DIR"

echo
echo "Done. Confirm the boot output with:"
echo "  arduino-cli monitor -p \"$PORT\" -c baudrate=115200"
echo "Expect:  crypto self-test: HMAC OK, AES OK"
