"""Phase 2 — the roster core in software/register_cards.py.

register_cards.py imports tkinter only inside run_gui(), so importing the module
for these tests is safe on a headless CI box.
"""
import csv

import pytest

import register_cards as rc

TOK_A = "a" * 32
TOK_B = "b" * 32
TOK_C = "c" * 32


# ------------------------------ normalize_key --------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0984257796", "0984257796"),
        ("0984257796\n", "0984257796"),
        ("  0984 257 796  ", "0984257796"),       # spaces stripped
        ("id=0984257796", "0984257796"),          # non-digits stripped
        ("", ""),
        ("no digits here", ""),
        ("1", "0000000001"),                      # zero-padded to 10
        ("4294967295", "4294967295"),             # 2**32 - 1, fits
        ("4294967296", "0000000000"),             # wraps mod 2**32
        ("10000000000", "1410065408"),            # 10**10 mod 2**32
    ],
)
def test_normalize_key(raw, expected):
    assert rc.normalize_key(raw) == expected


def test_normalize_key_none():
    assert rc.normalize_key(None) == ""


# ------------------------------ valid_andrew_id ----------------------
@pytest.mark.parametrize(
    "andrew_id, ok",
    [
        ("ab", True),           # 2 chars — lower bound
        ("mhilton1", True),     # 8 chars — upper bound
        ("jdoe", True),
        ("a", False),           # 1 char — too short
        ("", False),
        (None, False),
        ("mhilton12", False),   # 9 chars — too long
        ("waytoolongandrewid", False),
    ],
)
def test_valid_andrew_id(andrew_id, ok):
    assert rc.valid_andrew_id(andrew_id) is ok


# ------------------------- looks_like_card_scan -----------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0984257796", True),      # full card scan
        ("1234", True),            # short numeric scan, would pass valid_andrew_id's length check
        ("mhilton", False),        # real AndrewID
        ("mhilton1", False),       # real AndrewID with a digit
        ("", False),
        (None, False),
    ],
)
def test_looks_like_card_scan(raw, expected):
    assert rc.looks_like_card_scan(raw) is expected


# ------------------------ load_roster / save_roster ------------------
def test_load_roster_missing_file_is_empty(tmp_path):
    assert rc.load_roster(str(tmp_path / "roster.csv")) == {}


def test_load_roster_skips_header_blank_and_bad_tokens(tmp_path):
    p = tmp_path / "roster.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(
            [["token", "enc"], [], ["short", "x"], [TOK_A, "enc-a"], [TOK_B]],
        )
    roster = rc.load_roster(str(p))
    assert roster == {TOK_A: "enc-a", TOK_B: ""}   # missing enc field -> ""


def test_save_roster_writes_header_and_sorts(tmp_path):
    p = tmp_path / "roster.csv"
    rc.save_roster(str(p), {TOK_C: "enc-c", TOK_A: "enc-a", TOK_B: "enc-b"})
    rows = list(csv.reader(open(p, newline="", encoding="utf-8")))
    assert rows[0] == ["token", "enc"]
    assert rows[1:] == [[TOK_A, "enc-a"], [TOK_B, "enc-b"], [TOK_C, "enc-c"]]


def test_save_then_load_roundtrips(tmp_path):
    p = str(tmp_path / "roster.csv")
    original = {TOK_A: "enc-a", TOK_B: "enc-b"}
    rc.save_roster(p, original)
    assert rc.load_roster(p) == original


# --------------------------------- upsert --------------------------
def test_upsert_adds_new_entry(tmp_path):
    p = str(tmp_path / "roster.csv")
    (action, prev), count = rc.upsert(p, TOK_A, "enc-a")
    assert (action, prev, count) == ("added", None, 1)
    assert rc.load_roster(p) == {TOK_A: "enc-a"}


def test_upsert_updates_existing_and_returns_prev(tmp_path):
    p = str(tmp_path / "roster.csv")
    rc.upsert(p, TOK_A, "enc-old")
    (action, prev), count = rc.upsert(p, TOK_A, "enc-new")
    assert (action, prev, count) == ("updated", "enc-old", 1)
    assert rc.load_roster(p) == {TOK_A: "enc-new"}


def test_upsert_preserves_other_entries_and_counts(tmp_path):
    p = str(tmp_path / "roster.csv")
    rc.upsert(p, TOK_A, "enc-a")
    (_, _), count = rc.upsert(p, TOK_B, "enc-b")
    assert count == 2
    assert rc.load_roster(p) == {TOK_A: "enc-a", TOK_B: "enc-b"}


# ------------------------- registration log ---------------------------
def test_registration_log_path_sits_beside_roster():
    assert rc.registration_log_path("/x/y/roster.csv") == "/x/y/registration_log.csv"
    assert rc.registration_log_path("roster.csv") == "./registration_log.csv"


def test_log_registration_creates_file_with_header(tmp_path):
    p = str(tmp_path / "registration_log.csv")
    rc.log_registration(p, TOK_A)
    rows = list(csv.reader(open(p, newline="", encoding="utf-8")))
    assert rows[0] == ["timestamp", "token"]
    assert len(rows) == 2
    assert rows[1][1] == TOK_A


def test_log_registration_appends_without_rewriting_header(tmp_path):
    p = str(tmp_path / "registration_log.csv")
    rc.log_registration(p, TOK_A)
    rc.log_registration(p, TOK_B)
    rows = list(csv.reader(open(p, newline="", encoding="utf-8")))
    assert rows[0] == ["timestamp", "token"]
    assert [r[1] for r in rows[1:]] == [TOK_A, TOK_B]
