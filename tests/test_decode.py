"""Phase 2 — pure parsers in software/decode_attendance.py."""
import csv

import pytest

import attendance_crypto as ac
import decode_attendance as da

TOK_A = "a" * 32
TOK_B = "b" * 32


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return str(path)


# --------------------------- find_token_column -------------------------
@pytest.mark.parametrize(
    "header, expected",
    [
        (["time", "token"], 1),
        (["Token", "value"], 0),
        (["  TOKEN  ", "x"], 0),
        (["millis", "uid"], None),
        ([], None),
    ],
)
def test_find_token_column(header, expected):
    assert da.find_token_column(header) == expected


# ---------------------------- read_attendance ------------------------
def test_read_attendance_device_format(tmp_path):
    # millis,token with a header row that the 32-char filter drops
    path = _write_csv(
        tmp_path / "att.csv",
        [["timestamp", "token"], ["1000", TOK_A], ["2000", TOK_B]],
    )
    assert list(da.read_attendance(path)) == [("1000", TOK_A), ("2000", TOK_B)]


def test_read_attendance_device_format_skips_short_and_bad_rows(tmp_path):
    path = _write_csv(
        tmp_path / "att.csv",
        [["1000", TOK_A], ["oops"], ["3000", "tooshort"], ["4000", TOK_B]],
    )
    assert list(da.read_attendance(path)) == [("1000", TOK_A), ("4000", TOK_B)]


def test_read_attendance_sheet_export_named_columns(tmp_path):
    # a "token" header present -> sheet-export branch; time is column 0
    path = _write_csv(
        tmp_path / "sheet.csv",
        [["when", "token", "extra"], ["2026-08-27 10:00:00", TOK_A, "x"]],
    )
    assert list(da.read_attendance(path)) == [("2026-08-27 10:00:00", TOK_A)]


def test_read_attendance_sheet_export_token_first_column(tmp_path):
    # token is column 0 -> time_col falls to column 1
    path = _write_csv(
        tmp_path / "sheet.csv",
        [["token", "when"], [TOK_A, "2026-08-27 09:00:00"]],
    )
    assert list(da.read_attendance(path)) == [("2026-08-27 09:00:00", TOK_A)]


def test_read_attendance_sheet_export_single_column_time_equals_token(tmp_path):
    # Documented rough edge: token-only sheet export -> time field IS the token.
    path = _write_csv(tmp_path / "sheet.csv", [["token"], [TOK_A]])
    assert list(da.read_attendance(path)) == [(TOK_A, TOK_A)]


def test_read_attendance_empty_file(tmp_path):
    path = _write_csv(tmp_path / "empty.csv", [])
    assert list(da.read_attendance(path)) == []


# ----------------------------- token_to_name ------------------------
def test_token_to_name_decrypts(tmp_path, kat_key):
    tok = ac.token(kat_key, "0000000009")
    enc = ac.encrypt_name(kat_key, "Cara Osei")
    path = _write_csv(tmp_path / "roster.csv", [["token", "enc"], [tok, enc]])
    assert da.token_to_name(kat_key, path) == {tok: "Cara Osei"}


def test_token_to_name_missing_file_returns_empty(tmp_path, kat_key):
    # decode_attendance is lenient here (unlike build_gradebook.load_token_names)
    assert da.token_to_name(kat_key, str(tmp_path / "nope.csv")) == {}


def test_token_to_name_undecryptable_and_missing_enc(tmp_path, kat_key):
    path = _write_csv(
        tmp_path / "roster.csv",
        [[TOK_A, "notvalidhex"], [TOK_B]],   # bad hex, and a row with no enc field
    )
    out = da.token_to_name(kat_key, path)
    assert out[TOK_A] == "(could not decrypt)"
    assert out[TOK_B] == "(could not decrypt)"


# ------------------------------- decode() -------------------------------
def _roster(tmp_path, kat_key, registrations):
    import attendance_crypto as ac
    rows = [["token", "enc"]]
    for cid, name in registrations.items():
        rows.append([ac.token(kat_key, cid), ac.encrypt_name(kat_key, name)])
    return _write_csv(tmp_path / "roster.csv", rows)


def test_decode_maps_known_and_unknown(tmp_path, kat_key):
    import attendance_crypto as ac
    roster = _roster(tmp_path, kat_key, {"0000000001": "Alice Chen"})
    att = _write_csv(tmp_path / "att.csv", [
        ["timestamp", "token"],
        ["2026-08-27 10:00:00", ac.token(kat_key, "0000000001")],
        ["2026-08-27 10:01:00", "f" * 32],
    ])
    rows_out, unknown, registered = da.decode(att, roster, kat_key)
    assert rows_out == [
        ["2026-08-27 10:00:00", "Alice Chen"],
        ["2026-08-27 10:01:00", "UNKNOWN ffffffff"],
    ]
    assert (unknown, registered) == (1, 1)


def test_decode_missing_roster_is_all_unknown(tmp_path, kat_key):
    att = _write_csv(tmp_path / "att.csv", [["1000", TOK_A]])
    rows_out, unknown, registered = da.decode(att, str(tmp_path / "no.csv"), kat_key)
    assert rows_out == [["1000", f"UNKNOWN {TOK_A[:8]}"]]
    assert (unknown, registered) == (1, 0)


def test_write_report_has_header(tmp_path):
    out = tmp_path / "decoded.csv"
    da.write_report(str(out), [["t1", "Alice"], ["t2", "Bob"]])
    assert out.read_text().splitlines() == ["raw_time,name", "t1,Alice", "t2,Bob"]


def test_main_happy_path(tmp_path, kat_key, capsys):
    import attendance_crypto as ac
    (tmp_path / "secret.key").write_text(kat_key.hex())
    roster = _roster(tmp_path, kat_key, {"0000000001": "Alice Chen"})
    att = _write_csv(tmp_path / "att.csv", [
        ["timestamp", "token"],
        ["2026-08-27 10:00:00", ac.token(kat_key, "0000000001")],
    ])
    out = tmp_path / "decoded.csv"
    da.main([att, roster, "--key", str(tmp_path / "secret.key"), "--out", str(out)])
    printed = capsys.readouterr().out
    assert "Decoded 1 scans (0 unknown)" in printed
    assert "Roster had 1 registered students." in printed
    assert out.read_text().splitlines()[1] == "2026-08-27 10:00:00,Alice Chen"


def test_main_missing_key_exits(tmp_path):
    with pytest.raises(SystemExit):
        da.main(["att.csv", "roster.csv", "--key", str(tmp_path / "absent.key")])


def test_main_missing_attendance_exits(tmp_path, kat_key):
    (tmp_path / "secret.key").write_text(kat_key.hex())
    with pytest.raises(SystemExit):
        da.main([str(tmp_path / "gone.csv"), "roster.csv", "--key", str(tmp_path / "secret.key")])
