#!/usr/bin/env python3
"""
Download attendance.csv (or roster.csv) from the reader over USB serial.

Setup (once):   pip install pyserial

Usage:
    python3 sd_download.py                      # auto-detect port, save attendance.csv
    python3 sd_download.py --cmd roster         # save roster.csv instead
    python3 sd_download.py --cmd count          # just print the scan count
    python3 sd_download.py --port /dev/cu.usbserial-XXXX   # if auto-detect misses
    python3 sd_download.py --out ~/Desktop/class1.csv      # custom output file

The device stays plugged in via USB. Close the Arduino Serial Monitor first
(only one program can use the port at a time).
"""
import sys, time, argparse

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover
    sys.exit("pyserial is not installed.  Run:  pip install pyserial")


def find_port():
    for p in serial.tools.list_ports.comports():
        dev = (p.device or "")
        desc = (p.description or "").lower()
        if "usbserial" in dev or "wchusb" in dev.lower() or "ch340" in desc or "usbmodem" in dev:
            return p.device
    return None


# ---------------------- pure parsers (no serial I/O) ----------------------
def parse_dump(lines):
    """Collect the lines the device prints between its <<<BEGIN and <<<END markers."""
    out, capturing = [], False
    for line in lines:
        if line.startswith("<<<BEGIN"):
            capturing = True
            continue
        if line.startswith("<<<END"):
            break
        if capturing:
            out.append(line)
    return out


def parse_count(lines):
    """Pull N out of the device's 'attendance rows: N' reply, or None."""
    for raw in lines:
        line = raw.strip()
        if line.startswith("attendance rows:"):
            try:
                return int(line.split(":", 1)[1])
            except ValueError:
                return None
    return None


def _serial_lines(ser, timeout_s):  # pragma: no cover  (hardware I/O)
    """Yield decoded, newline-stripped lines from `ser` until `timeout_s` elapses."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        raw = ser.readline()
        if not raw:
            continue
        yield raw.decode("utf-8", "replace").rstrip("\r\n")


def main():  # pragma: no cover  (opens a real serial port)
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port (auto-detected if omitted)")
    ap.add_argument("--cmd", default="dump", help="dump | roster | count")
    ap.add_argument("--out", help="output file (default depends on --cmd)")
    ap.add_argument("--baud", type=int, default=115200)
    a = ap.parse_args()

    port = a.port or find_port()
    if not port:
        sys.exit("No serial port found. Plug the device in, or pass --port /dev/cu.usbserial-...")
    out = a.out or {"dump": "attendance.csv", "roster": "roster.csv"}.get(a.cmd, a.cmd + ".txt")

    print(f"Port {port} @ {a.baud}, command '{a.cmd}'")
    ser = serial.Serial(port, a.baud, timeout=2)
    time.sleep(2.0)                 # the ESP32 reboots when the port opens; wait for boot
    ser.reset_input_buffer()
    ser.write((a.cmd + "\n").encode())

    if a.cmd == "count":
        n = parse_count(_serial_lines(ser, 6))
        ser.close()
        if n is not None:
            print(f"attendance rows: {n}")
        return

    lines = parse_dump(_serial_lines(ser, 20))
    ser.close()

    if not lines:
        sys.exit("No data captured. Is the PN532 sketch flashed, an SD card inserted, "
                 "and the Serial Monitor closed?")
    with open(out, "w", newline="") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved {len(lines)} lines to {out}")


if __name__ == "__main__":
    main()
