#!/usr/bin/env python3
r"""
Upload a new roster.csv to the reader over USB serial — no SD card removal.

Setup (once):   pip install pyserial

Usage:
    python3 sd_upload.py                        # auto-detect port, send ./roster.csv
    python3 sd_upload.py myclass.csv            # send a different file
    python3 sd_upload.py --port /dev/cu.usbserial-XXXX   # if auto-detect misses
    python3 sd_upload.py --baud 115200
    python3 sd_upload.py --scan                 # list serial devices connected right now
    python3 sd_upload.py help                   # print this help and exit

The device must be running the attendance_reader_PN532 sketch with an SD card
inserted. Close the Arduino Serial Monitor first (only one program can use the
port at a time). Verify afterwards with:  python3 sd_download.py --cmd roster

Protocol: host sends "upload\n"; device replies "<<<READY>>>"; host sends
"<length> <checksum>\n" then <length> raw bytes (checksum = sum of the bytes,
32-bit wrap). The device streams to a temp file, verifies size + checksum,
atomically renames it over roster.csv, reloads the roster, and prints
"<<<OK roster.csv N bytes, M entries>>>".
"""
import sys, time, argparse

try:
    import serial
    import serial.tools.list_ports
except ImportError:  # pragma: no cover
    sys.exit("pyserial is not installed.  Run:  pip install pyserial")

# find_port() and the line reader are shared with the download side.
from sd_download import find_port, _serial_lines

MAX_BYTES = 200_000   # must match the cap in recvRoster() on the device


# ---------------------- pure helpers (no serial I/O) ----------------------
def checksum(data: bytes) -> int:
    """Sum of every byte, wrapped to 32 bits — matches the firmware's check."""
    return sum(data) & 0xFFFFFFFF


def build_header(data: bytes) -> str:
    """The '<length> <checksum>' line the device reads before the raw bytes."""
    return f"{len(data)} {checksum(data)}"


def find_marker(lines, *prefixes):
    """First line that starts with any of `prefixes`, or None."""
    for line in lines:
        if any(line.startswith(p) for p in prefixes):
            return line
    return None


def parse_result(lines):
    """(ok, message) from the device's '<<<OK ...>>>' / '<<<ERR ...>>>' reply."""
    line = find_marker(lines, "<<<OK", "<<<ERR")
    if line is None:
        return False, "no reply from device"
    return line.startswith("<<<OK"), line.strip("<> ")


def describe_ports(ports, chosen=None):
    """Human-readable lines for a list of serial-port entries.

    `ports` is what serial.tools.list_ports.comports() returns (each has
    .device / .description / .hwid). `chosen` is the device string find_port()
    would auto-pick; that row is flagged with '->'.
    """
    if not ports:
        return ["No serial ports found. Plug the device in via USB."]
    rows = []
    for p in ports:
        mark = "->" if chosen and p.device == chosen else "  "
        desc = getattr(p, "description", None) or "?"
        hwid = getattr(p, "hwid", None) or "?"
        rows.append(f"{mark} {p.device}    {desc}    [{hwid}]")
    rows.append("")
    if chosen:
        rows.append(f"Auto-detect would use: {chosen}")
    else:
        rows.append("Auto-detect found no likely match — pass --port explicitly.")
    return rows


def main():  # pragma: no cover  (opens a real serial port)
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", default="roster.csv",
                    help="local CSV to upload (default: roster.csv); "
                         "'help' prints this help and exits")
    ap.add_argument("--port", help="serial port (auto-detected if omitted)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--scan", action="store_true",
                    help="list the serial devices connected right now and exit")
    a = ap.parse_args()

    if a.file == "help" and not a.scan:
        ap.print_help()
        return

    if a.scan:
        ports = list(serial.tools.list_ports.comports())
        print("\n".join(describe_ports(ports, find_port())))
        return

    try:
        with open(a.file, "rb") as fh:
            data = fh.read()
    except OSError as e:
        sys.exit(f"can't read {a.file}: {e}")
    if not data:
        sys.exit(f"{a.file} is empty — nothing to upload")
    if len(data) > MAX_BYTES:
        sys.exit(f"{a.file} is {len(data)} bytes; the device caps roster.csv at {MAX_BYTES}")

    port = a.port or find_port()
    if not port:
        sys.exit("No serial port found. Plug the device in, or pass --port /dev/cu.usbserial-...")

    print(f"Port {port} @ {a.baud} — sending {a.file} ({len(data)} bytes)")
    ser = serial.Serial(port, a.baud, timeout=2)
    time.sleep(2.0)                 # the ESP32 reboots when the port opens; wait for boot
    ser.reset_input_buffer()

    ser.write(b"upload\n")
    reply = find_marker(_serial_lines(ser, 10), "<<<READY", "<<<ERR")
    if reply is None:
        ser.close()
        sys.exit("device never sent <<<READY>>>. Wrong sketch, or the Arduino "
                 "Serial Monitor is still open?")
    if reply.startswith("<<<ERR"):
        ser.close()
        sys.exit(f"device refused upload: {reply.strip('<> ')}")

    ser.write((build_header(data) + "\n").encode())
    ser.flush()
    # Send the payload in small chunks with a brief pause between them. The
    # device drains each chunk to the SD card before reading the next; blasting
    # the whole file at once overruns its 256-byte serial buffer while it is
    # busy writing, silently dropping bytes (symptom: "<<<ERR got X/Y bytes>>>").
    CHUNK = 128
    for i in range(0, len(data), CHUNK):
        ser.write(data[i:i + CHUNK])
        ser.flush()
        time.sleep(0.02)

    ok, msg = parse_result(_serial_lines(ser, 30))
    ser.close()
    print(msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
