"""Phase 2 — pure helpers in software/build_gradebook.py.

No refactor: these functions are already module-level and side-effect free
(load_token_names / load_aliases only read files).
"""
import csv

import pytest

import attendance_crypto as ac
import build_gradebook as bg


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    return str(path)


# ------------------------------ norm_tokens ------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Chen, Alice", ("alice", "chen")),
        ("alice chen", ("alice", "chen")),                  # order-independent
        ("ALICE   CHEN", ("alice", "chen")),                # case + whitespace
        ("O'Brien-Smith, Pat", ("brien", "o", "pat", "smith")),  # punctuation -> split
        ("", ()),
        (None, ()),
        ("   ", ()),
        ("Bob 3rd", ("3rd", "bob")),                        # digits kept
    ],
)
def test_norm_tokens(raw, expected):
    assert bg.norm_tokens(raw) == expected


def test_norm_tokens_is_order_and_punctuation_independent():
    assert bg.norm_tokens("Alice B. Chen") == bg.norm_tokens("chen, alice b")


def test_norm_tokens_dedupes_nothing_but_sorts():
    # repeated tokens are preserved (it's a sorted tuple, not a set)
    assert bg.norm_tokens("aa aa bb") == ("aa", "aa", "bb")


# ------------------------------ fmt_points ------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [
        (1.0, "1"),
        (0.0, "0"),
        (2.0, "2"),
        (0.5, "0.5"),
        (0.25, "0.25"),
        (0.75, "0.75"),
        (1.0 - 1e-12, "1"),          # within integer tolerance
        (2.0 / 3.0, "0.6667"),       # rounded to 4dp, trailing handled
        (0.1, "0.1"),
    ],
)
def test_fmt_points(value, expected):
    assert bg.fmt_points(value) == expected


# ------------------------------- col_label -----------------------------
@pytest.mark.parametrize(
    "header, expected",
    [
        ("Jan 20 Activity (995978)", "jan 20 activity"),
        ("Aug 26 Activity (999001)", "aug 26 activity"),
        ("  Participation  ", "participation"),
        ("Quiz (12) results", "quiz (12) results"),   # parens not at end: kept
        ("", ""),
        (None, ""),
    ],
)
def test_col_label(header, expected):
    assert bg.col_label(header) == expected


# --------------------------- load_token_names -------------------------
def test_load_token_names_decrypts_roster(tmp_path, kat_key):
    tok = ac.token(kat_key, "0000000001")
    enc = ac.encrypt_name(kat_key, "Alice Chen")
    path = _write_csv(tmp_path / "roster.csv", [["token", "enc"], [tok, enc]])
    assert bg.load_token_names(kat_key, path) == {tok: "Alice Chen"}


def test_load_token_names_skips_header_and_short_rows(tmp_path, kat_key):
    tok = ac.token(kat_key, "0000000002")
    enc = ac.encrypt_name(kat_key, "Bob Diaz")
    path = _write_csv(
        tmp_path / "roster.csv",
        [["token", "enc"], [], ["not-a-token"], [tok, enc]],
    )
    assert bg.load_token_names(kat_key, path) == {tok: "Bob Diaz"}


def test_load_token_names_marks_undecryptable(tmp_path, kat_key):
    tok = "a" * 32
    path = _write_csv(tmp_path / "roster.csv", [[tok, "deadbeef"]])
    assert bg.load_token_names(kat_key, path) == {tok: "(decrypt failed)"}


def test_load_token_names_exits_when_missing(tmp_path, kat_key):
    with pytest.raises(SystemExit):
        bg.load_token_names(kat_key, str(tmp_path / "nope.csv"))


# ----------------------------- load_aliases --------------------------
def test_load_aliases_normalizes_and_lowercases(tmp_path):
    path = _write_csv(
        tmp_path / "aliases.csv",
        [
            ["typed_name", "sis_login_id"],
            ["Mike Smith", "MSmith2@Example.edu"],
            ["", ""],                         # blank -> skipped
            ["OnlyOneField"],                 # < 2 fields -> skipped
        ],
    )
    m = bg.load_aliases(path)
    assert m == {("mike", "smith"): "msmith2@example.edu"}


def test_load_aliases_missing_or_none_returns_empty(tmp_path):
    assert bg.load_aliases(None) == {}
    assert bg.load_aliases(str(tmp_path / "absent.csv")) == {}
