"""software/recover_sessions.py: the read_rows()/sessionize()/parse_map() parsers and main()."""
import csv

import pytest

import attendance_crypto as ac
import helpers
import recover_sessions as rs
import register_cards as rc

TOK_A = "a" * 32
TOK_B = "b" * 32


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return str(path)


# ------------------------------- read_rows -------------------------------
def test_read_rows_skips_three_column_test_format(tmp_path):
    path = _write_csv(tmp_path / "att.csv", [
        ["1000", "cardid", "name"],           # 3-col legacy test row: skipped
        ["unsynced-500", TOK_A],
    ])
    assert list(rs.read_rows(path)) == [(2, "unsynced-500", TOK_A)]


def test_read_rows_drops_truncated_token(tmp_path):
    path = _write_csv(tmp_path / "att.csv", [
        ["unsynced-500", "short"],
        ["unsynced-600", TOK_A],
    ])
    assert list(rs.read_rows(path)) == [(2, "unsynced-600", TOK_A)]


def test_read_rows_drops_garbled_timestamp(tmp_path):
    # A torn SD write can NUL-pad a timestamp; it doesn't start with 'unsynced-'
    # so without validation it would be misread as a real synced row.
    garbled = "un" + "\x00" * 400 + "unsynced-999"
    path = _write_csv(tmp_path / "att.csv", [
        [garbled, TOK_A],
        ["unsynced-600", TOK_B],
    ])
    assert list(rs.read_rows(path)) == [(2, "unsynced-600", TOK_B)]


def test_read_rows_accepts_real_synced_timestamp(tmp_path):
    path = _write_csv(tmp_path / "att.csv", [["2026-08-28 09:00:00", TOK_A]])
    assert list(rs.read_rows(path)) == [(1, "2026-08-28 09:00:00", TOK_A)]


# ------------------------------- sessionize -------------------------------
def _rows(*ts_list):
    return [(i + 1, ts, TOK_A) for i, ts in enumerate(ts_list)]


def test_sessionize_single_session_of_increasing_millis():
    sessions = rs.sessionize(_rows("unsynced-100", "unsynced-200", "unsynced-300"))
    assert len(sessions) == 1
    assert len(sessions[0]) == 3


def test_sessionize_splits_on_millis_going_backwards():
    sessions = rs.sessionize(_rows("unsynced-100", "unsynced-200", "unsynced-50"))
    assert [len(s) for s in sessions] == [2, 1]


def test_sessionize_splits_on_synced_to_unsynced_transition():
    sessions = rs.sessionize(_rows("2026-08-28 09:00:00", "unsynced-50"))
    assert [len(s) for s in sessions] == [1, 1]


def test_sessionize_does_not_split_on_unsynced_to_synced_transition():
    # a real synced row doesn't reset millis, so it stays in the same session
    sessions = rs.sessionize(_rows("unsynced-50", "2026-08-28 09:00:00"))
    assert len(sessions) == 1


def test_sessionize_a_garbled_row_dropped_by_read_rows_does_not_fracture_a_session(tmp_path):
    # Regression: a NUL-padded timestamp used to read as 'synced' and split one
    # real session into two. read_rows() now drops it before sessionize() sees it.
    garbled = "un" + "\x00" * 30
    path = _write_csv(tmp_path / "att.csv", [
        ["unsynced-100", TOK_A],
        [garbled, TOK_A],
        ["unsynced-200", TOK_A],
    ])
    rows = list(rs.read_rows(path))
    sessions = rs.sessionize(rows)
    assert len(sessions) == 1
    assert len(sessions[0]) == 2


def test_read_rows_skips_empty_token(tmp_path):
    path = _write_csv(tmp_path / "att.csv", [["unsynced-500", ""], ["unsynced-600", TOK_A]])
    assert list(rs.read_rows(path)) == [(2, "unsynced-600", TOK_A)]


# ---------------------------- describe_session ----------------------------
def test_describe_session_unsynced_span_and_cards():
    sess = [(3, "unsynced-0", TOK_A, "unsynced", 0),
            (4, "unsynced-600000", TOK_B, "unsynced", 600000)]
    assert rs.describe_session(2, sess) == \
        "session 2: 2 taps, 2 cards, lines 3-4, 10 min span  (unmapped)"


def test_describe_session_shows_synced_range_and_mapped_date():
    sess = [(1, "2026-08-27 10:00:00", TOK_A, "synced", None),
            (2, "2026-08-27 10:05:00", TOK_A, "synced", None)]
    assert rs.describe_session(1, sess, "2026-08-27") == (
        "session 1: 2 taps, 1 cards, lines 1-2, "
        "synced 2026-08-27 10:00:00 .. 2026-08-27 10:05:00  -> 2026-08-27")


# ------------------------------- parse_map -------------------------------
def test_parse_map_builds_session_to_date_dict():
    assert rs.parse_map(["1=2026-08-28", "3=2026-09-08"]) == {1: "2026-08-28", 3: "2026-09-08"}


def test_parse_map_rejects_bad_date():
    with pytest.raises(ValueError):
        rs.parse_map(["1=2026-13-40"])


# --------------------------------- main ----------------------------------
def test_main_end_to_end(tmp_path, capsys):

    key = tmp_path / "secret.key"
    key.write_text(helpers.KAT_KEY.hex())
    alice, bob, stranger = (helpers.tok(c) for c in ("0000000001", "0000000002", "0000000009"))
    roster = str(tmp_path / "roster.csv")
    rc.save_roster(roster, {alice: ac.encrypt_name(helpers.KAT_KEY, "alice"),
                            bob: "not-valid-ciphertext"})

    att = _write_csv(tmp_path / "att.csv", [
        ["2026-08-27 10:00:00", alice],    # synced row in session 1 (unmapped): kept as-is
        ["unsynced-1000", alice],          # session 2 (unmapped, unsynced): dropped
        ["unsynced-500", alice],           # millis reset -> session 3, mapped
        ["unsynced-65500", bob],           #   +65 s
        ["unsynced-125500", stranger],     #   +125 s, not in roster
        ["2026-08-28 10:30:00", bob],      #   synced row inside a mapped session: kept
    ])
    out = str(tmp_path / "recovered.csv")
    rs.main([att, "--map", "3=2026-08-28", "--out", out,
             "--roster", roster, "--key", str(key)])

    rows = list(csv.reader(open(out, newline="", encoding="utf-8")))
    assert rows == [
        ["timestamp", "token"],
        ["2026-08-27 10:00:00", alice],
        ["2026-08-28 00:00:00", alice],
        ["2026-08-28 00:01:05", bob],
        ["2026-08-28 00:02:05", stranger],
        ["2026-08-28 10:30:00", bob],
    ]
    report = capsys.readouterr().out
    assert "session 1: 1 taps" in report and "session 2: 1 taps" in report
    assert "session 3: 4 taps, 3 cards, lines 3-6, 2 min span, synced 2026-08-28 10:30:00" in report
    assert "=== 2026-08-28  (3 present) ===" in report
    assert "alice" in report and "(could not decrypt)" in report
    assert f"UNREGISTERED {stranger[:8]}" in report


def test_main_without_roster_labels_everyone_unregistered(tmp_path, capsys):
    key = tmp_path / "secret.key"
    key.write_text(helpers.KAT_KEY.hex())
    att = _write_csv(tmp_path / "att.csv", [["unsynced-5", TOK_A]])
    rs.main([att, "--map", "1=2026-08-28", "--out", str(tmp_path / "o.csv"),
             "--roster", str(tmp_path / "none.csv"), "--key", str(key)])
    assert f"UNREGISTERED {TOK_A[:8]}" in capsys.readouterr().out
