"""Phase 3 — pure parsers split out of sd_download.main()."""
import sd_download as sd


# ------------------------------- parse_dump -------------------------------
def test_parse_dump_captures_between_markers():
    lines = [
        "boot noise",
        "<<<BEGIN attendance.csv>>>",
        "timestamp,token",
        "2026-08-27 10:00:00,abcd",
        "<<<END attendance.csv>>>",
        "trailing noise",
    ]
    assert sd.parse_dump(lines) == ["timestamp,token", "2026-08-27 10:00:00,abcd"]


def test_parse_dump_without_markers_is_empty():
    assert sd.parse_dump(["just", "some", "lines"]) == []


def test_parse_dump_begin_without_end_returns_what_it_saw():
    lines = ["<<<BEGIN roster.csv>>>", "token,enc", "aaaa,bbbb"]
    assert sd.parse_dump(lines) == ["token,enc", "aaaa,bbbb"]


def test_parse_dump_empty_capture():
    assert sd.parse_dump(["<<<BEGIN x>>>", "<<<END x>>>"]) == []


# ------------------------------- parse_count ------------------------------
def test_parse_count_reads_number():
    assert sd.parse_count(["booting", "attendance rows: 42", "more"]) == 42


def test_parse_count_strips_whitespace():
    assert sd.parse_count(["  attendance rows: 7  \r\n"]) == 7


def test_parse_count_absent_returns_none():
    assert sd.parse_count(["nothing", "relevant"]) is None


def test_parse_count_non_numeric_returns_none():
    assert sd.parse_count(["attendance rows: lots"]) is None


# -------------------------------- find_port ------------------------------
class _Port:
    def __init__(self, device, description=""):
        self.device = device
        self.description = description


def test_find_port_matches_usbserial(monkeypatch):
    monkeypatch.setattr(
        sd.serial.tools.list_ports, "comports",
        lambda: [_Port("/dev/cu.Bluetooth"), _Port("/dev/cu.usbserial-1420")],
    )
    assert sd.find_port() == "/dev/cu.usbserial-1420"


def test_find_port_matches_ch340_description(monkeypatch):
    monkeypatch.setattr(
        sd.serial.tools.list_ports, "comports",
        lambda: [_Port("/dev/ttyS0", "USB CH340 serial")],
    )
    assert sd.find_port() == "/dev/ttyS0"


def test_find_port_none_when_no_match(monkeypatch):
    monkeypatch.setattr(
        sd.serial.tools.list_ports, "comports",
        lambda: [_Port("/dev/cu.Bluetooth-Incoming-Port")],
    )
    assert sd.find_port() is None
