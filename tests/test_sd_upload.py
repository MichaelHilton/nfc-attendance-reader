"""Pure helpers split out of sd_upload.main(): checksum / header framing and
reply-marker parsing. The serial I/O in main() is `# pragma: no cover`, same as
test_sd_download.py."""
import sd_upload as su


# ------------------------------- checksum --------------------------------
def test_checksum_sums_bytes():
    assert su.checksum(b"\x01\x02\x03") == 6


def test_checksum_empty_is_zero():
    assert su.checksum(b"") == 0


def test_checksum_masked_to_32_bits(monkeypatch):
    # checksum() calls the builtin sum(); shadow it with a value above 2**32 to
    # prove the 0xFFFFFFFF mask is applied (a real roster never gets that large).
    monkeypatch.setattr(su, "sum", lambda data: 0x1_2345_6789, raising=False)
    assert su.checksum(b"anything") == 0x2345_6789


# ------------------------------ build_header -----------------------------
def test_build_header_is_length_space_checksum():
    data = b"token,enc\n"
    assert su.build_header(data) == f"10 {su.checksum(data)}"


def test_build_header_empty():
    assert su.build_header(b"") == "0 0"


# ------------------------------ find_marker ------------------------------
def test_find_marker_returns_first_match():
    assert su.find_marker(["boot", "<<<READY>>>", "junk"], "<<<READY") == "<<<READY>>>"


def test_find_marker_accepts_multiple_prefixes():
    lines = ["noise", "<<<ERR bad header>>>"]
    assert su.find_marker(lines, "<<<OK", "<<<ERR") == "<<<ERR bad header>>>"


def test_find_marker_none_when_absent():
    assert su.find_marker(["a", "b"], "<<<OK") is None


# ------------------------------ parse_result ----------------------------
def test_parse_result_ok():
    ok, msg = su.parse_result(["boot noise", "<<<OK roster.csv 812 bytes, 24 entries>>>"])
    assert ok is True
    assert msg == "OK roster.csv 812 bytes, 24 entries"


def test_parse_result_err():
    ok, msg = su.parse_result(["<<<ERR got 400/812 bytes, sum 1/2>>>"])
    assert ok is False
    assert msg == "ERR got 400/812 bytes, sum 1/2"


def test_parse_result_no_reply():
    ok, msg = su.parse_result(["just", "boot", "noise"])
    assert ok is False
    assert "no reply" in msg


# ------------------------------ describe_ports --------------------------
class _Port:
    def __init__(self, device, description="", hwid=""):
        self.device = device
        self.description = description
        self.hwid = hwid


def test_describe_ports_empty_list():
    assert su.describe_ports([]) == [
        "No serial ports found. Plug the device in via USB."
    ]


def test_describe_ports_flags_the_auto_detected_row():
    ports = [_Port("/dev/cu.Bluetooth"), _Port("/dev/cu.usbserial-1420", "CP2102", "USB VID:PID=10C4:EA60")]
    lines = su.describe_ports(ports, chosen="/dev/cu.usbserial-1420")
    assert lines[0].startswith("   /dev/cu.Bluetooth")
    assert lines[1].startswith("-> /dev/cu.usbserial-1420")
    assert "CP2102" in lines[1] and "USB VID:PID=10C4:EA60" in lines[1]
    assert lines[-1] == "Auto-detect would use: /dev/cu.usbserial-1420"


def test_describe_ports_notes_when_nothing_matches():
    lines = su.describe_ports([_Port("/dev/cu.Bluetooth")], chosen=None)
    assert not any(line.startswith("->") for line in lines)
    assert lines[-1] == "Auto-detect found no likely match — pass --port explicitly."


def test_describe_ports_fills_blanks_for_missing_metadata():
    lines = su.describe_ports([_Port("/dev/ttyUSB0")], chosen="/dev/ttyUSB0")
    assert "?    [?]" in lines[0]
