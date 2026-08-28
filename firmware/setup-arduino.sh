#!/usr/bin/env bash
# Install everything firmware/flash.sh needs: arduino-cli, the ESP32 core, and the
# three libraries. Safe to re-run -- arduino-cli skips what is already installed.
# Works in the devcontainer and on a Linux/macOS host.
#
#   ./firmware/setup-arduino.sh
#   BINDIR=/usr/local/bin ./firmware/setup-arduino.sh   # pick where arduino-cli lands
set -euo pipefail

BINDIR="${BINDIR:-$HOME/.local/bin}"
export PATH="$BINDIR:$PATH"   # so a re-run finds an arduino-cli we installed before

if ! command -v arduino-cli >/dev/null; then
	echo "==> installing arduino-cli into $BINDIR"
	mkdir -p "$BINDIR"
	curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
		| BINDIR="$BINDIR" sh
	echo "NOTE: $BINDIR is not on macOS's default PATH. firmware/flash.sh adds it"
	echo "      itself, but for an 'arduino-cli' you can run directly, add to ~/.zshrc:"
	echo "        export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo "==> updating package index"
arduino-cli core update-index

echo "==> installing esp32:esp32 core (large -- a few minutes the first time)"
arduino-cli core install esp32:esp32

echo "==> installing libraries"
arduino-cli lib install "TFT_eSPI" "Adafruit PN532" "Adafruit BusIO"

# The downloaded core/toolchain archives (~1.5 GB) are only needed during install.
rm -rf "${HOME}/.arduino15/staging" 2>/dev/null || true

echo
echo "Done. Compile check:  ./firmware/flash.sh -n"
echo "TFT_eSPI still needs a User_Setup.h for the 3.5\" ST7796 CYD -- see docs/DESIGN_NOTES.md."
