"""Shared builders for the gradebook tests.

pytest's default (prepend) import mode puts tests/ on sys.path, so tests can
`import helpers`.
"""
import csv
import pathlib

import attendance_crypto as ac

KAT_KEY = bytes(range(32))

CANVAS_HEADER = [
    "Student", "ID", "SIS User ID", "SIS Login ID",
    "Root Account", "Section", "Wk1 Activity (900001)",
]
POINTS_ROW = ["Points Possible", "", "", "", "", "", "2.00"]


def tok(card_id, key=KAT_KEY):
    return ac.token(key, card_id)


def uid_to_key(uid_bytes):
    """Reproduce the firmware's uidToKey(): first 4 UID bytes, little-endian, as a
    zero-padded 10-digit decimal -- the same string the USB registration reader
    types. (attendance_reader_PN532.ino :: uidToKey)"""
    v = 0
    for i, b in enumerate(bytes(uid_bytes)[:4]):
        v |= b << (8 * i)
    return f"{v:010d}"


def simulate_tap(card_id, when, key=KAT_KEY):
    """One attendance.csv row exactly as the firmware writes it on a tap:
    [timestamp, token] where token = HMAC-SHA256(KMAC, id)[:16] hex."""
    return [when.strftime("%Y-%m-%d %H:%M:%S"), ac.token(key, card_id)]


def _csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def canvas_rows(students, *, header=CANVAS_HEADER, points=POINTS_ROW):
    """students: iterable of (display_name, sis_login_id). Trailing activity
    column starts blank."""
    rows = [list(header), list(points)]
    for name, login in students:
        row = [name, "1000", "u", login, "School", "Sec 1", ""]
        rows.append(row)
    return rows


def make_files(tmp_path, *, canvas, registrations, taps, aliases=None, key=KAT_KEY):
    """Write canvas/roster/attendance(/aliases) CSVs; return their paths.

    registrations: {card_id: typed_name}
    taps:          list of [timestamp, token]  (use helpers.tok(card_id))
    aliases:       list of [typed_name, sis_login_id] or None
    """
    d = pathlib.Path(tmp_path)
    _csv(d / "canvas.csv", canvas)

    roster = {ac.token(key, cid): ac.encrypt_name(key, nm)
              for cid, nm in registrations.items()}
    _csv(d / "roster.csv", [["token", "enc"]] + [[t, roster[t]] for t in sorted(roster)])

    _csv(d / "attendance.csv", [["timestamp", "token"]] + taps)

    aliases_path = d / "aliases.csv"
    if aliases is not None:
        _csv(aliases_path, [["typed_name", "sis_login_id"]] + aliases)

    return {
        "canvas": str(d / "canvas.csv"),
        "roster": str(d / "roster.csv"),
        "attendance": str(d / "attendance.csv"),
        "aliases": str(aliases_path) if aliases is not None else str(d / "missing.csv"),
    }
