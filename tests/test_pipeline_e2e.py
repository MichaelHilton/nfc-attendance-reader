"""Phase 4 — golden end-to-end test of the whole laptop pipeline.

    generate key -> register cards (roster.csv) -> simulate a class of taps
    (attendance.csv, as the firmware writes it) -> decode_attendance -> build_gradebook

No hardware. helpers.simulate_tap() is the firmware oracle: it produces the exact
'timestamp,token' rows attendance_reader_PN532.ino logs on a tap. The decoded
report and the filled Canvas CSV are compared byte-for-byte against committed
golden files; regenerate them with:  pytest --update-golden
"""
import datetime as dt
import pathlib

import pytest

import attendance_crypto as ac
import build_gradebook as bg
import decode_attendance as da
import register_cards as rc
import helpers
from conftest import assert_golden

FIX = pathlib.Path(__file__).parent / "fixtures" / "pipeline"
GOLDEN = FIX / "golden"

# card id (what the USB reader types) -> name typed at registration
REGISTRATIONS = [
    ("0000000001", "Alice Chen"),     # exact match to Canvas "Chen, Alice"
    ("0000000002", "Bob Diaz"),       # exact
    ("0000000003", "Cara Osei"),      # exact
    ("0000000004", "David Nguyen"),   # approx: Canvas has "Nguyen, David M"
    ("0000000005", "Ick Park"),       # alias -> eun.park@example.edu (aliases.csv)
    ("0000000009", "Ghost Student"),  # registered but not in Canvas -> unmatched
]

SESSION = bg.Session(date="2026-08-27", start="10:00",
                     late_after=10.0, close=30.0, late_frac=0.5,
                     column="Aug 27 Activity")


def _at(hh, mm, ss=0, day=27):
    return dt.datetime(2026, 8, day, hh, mm, ss)


def _build_inputs(tmp_path):
    """Create secret.key, roster.csv and attendance.csv in tmp_path the way the
    real tools would, and return their paths."""
    key_path = tmp_path / "secret.key"
    key_path.write_text(helpers.KAT_KEY.hex())
    K = ac.load_or_create_key(str(key_path))       # exercises load + validate

    # --- registration: build roster.csv through register_cards' core ---
    roster_path = tmp_path / "roster.csv"
    for raw_card, name in REGISTRATIONS:
        card_id = rc.normalize_key(raw_card)
        rc.upsert(str(roster_path), ac.token(K, card_id), ac.encrypt_name(K, name))

    # --- a class's worth of taps, exactly as the firmware would log them ---
    taps = [
        helpers.simulate_tap("0000000001", _at(9, 58)),     # present (before start)
        helpers.simulate_tap("0000000002", _at(10, 7, 30)),  # present (<= 10 min)
        helpers.simulate_tap("0000000003", _at(10, 18)),     # late (<= 30 min)
        helpers.simulate_tap("0000000004", _at(10, 45)),     # absent (after close)
        helpers.simulate_tap("0000000005", _at(10, 3)),      # present (via alias)
        helpers.simulate_tap("0000000009", _at(10, 5)),      # unmatched name
        ["2026-08-27 10:06:00", "deadbeef" * 4],             # unregistered token
        ["unsynced-12345", ac.token(K, "0000000002")],       # NTP not set yet
        helpers.simulate_tap("0000000001", _at(10, 0, day=26)),  # wrong day -> ignored
        helpers.simulate_tap("0000000001", _at(10, 2)),      # earliest tap already stands
    ]
    att_path = tmp_path / "attendance.csv"
    with open(att_path, "w", newline="", encoding="utf-8") as f:
        import csv
        w = csv.writer(f)
        w.writerow(["timestamp", "token"])
        w.writerows(taps)

    return K, str(roster_path), str(att_path)


def test_decode_stage_matches_golden(tmp_path, update_golden):
    K, roster_path, att_path = _build_inputs(tmp_path)

    rows_out, unknown, registered = da.decode(att_path, roster_path, K)
    assert (unknown, registered) == (1, len(REGISTRATIONS))

    out = tmp_path / "decoded.csv"
    da.write_report(str(out), rows_out)
    assert_golden(GOLDEN / "decoded.csv", out.read_text(), update_golden)


def test_gradebook_stage_matches_golden(tmp_path, monkeypatch, update_golden):
    K, roster_path, att_path = _build_inputs(tmp_path)

    # Run from the fixtures dir so the report echoes a portable "aliases.csv"
    # rather than a machine-specific absolute path.
    monkeypatch.chdir(FIX)
    result = bg.build("Grades.csv", att_path, roster_path, "aliases.csv", K, SESSION)

    assert (result.present, result.late, result.absent) == (3, 1, 1)
    assert result.enrolled == 5
    assert result.unsynced == 1
    assert result.unmatched == ["Ghost Student"]
    assert result.ambiguous == []
    assert result.unregistered == ["deadbeef"]
    assert result.target_header == "Aug 27 Activity (999002)"
    assert (result.full_pts, result.late_pts) == (2.0, 1.0)

    filled = tmp_path / "Grades_filled.csv"
    bg.write_output(str(filled), result.rows)
    assert_golden(GOLDEN / "Grades_filled.csv", filled.read_text(), update_golden)
    assert_golden(
        GOLDEN / "report.txt",
        bg.render_report(result, SESSION, "Grades_filled.csv"),
        update_golden,
    )


def test_only_target_column_changed_from_canvas_input(tmp_path):
    """The filled CSV differs from the Canvas export in exactly one column."""
    K, roster_path, att_path = _build_inputs(tmp_path)
    result = bg.build(str(FIX / "Grades.csv"), att_path, roster_path,
                      str(FIX / "aliases.csv"), K, SESSION)

    import csv
    original = list(csv.reader(open(FIX / "Grades.csv", newline="", encoding="utf-8")))
    assert len(result.rows) == len(original)
    target = original[0].index("Aug 27 Activity (999002)")
    for orig_row, new_row in zip(original[2:], result.rows[2:]):
        for c in range(len(orig_row)):
            if c != target:
                assert new_row[c] == orig_row[c]


@pytest.mark.parametrize(
    "uid, expected",
    [
        (bytes([0x04, 0x95, 0xAA, 0x3A, 0xCF, 0x22, 0x90]), "0984257796"),  # DESIGN_NOTES §2
        (bytes([0x01, 0x00, 0x00, 0x00]), "0000000001"),
        (bytes([0xFF, 0xFF, 0xFF, 0xFF]), "4294967295"),
    ],
)
def test_uid_to_key_matches_firmware(uid, expected):
    assert helpers.uid_to_key(uid) == expected
