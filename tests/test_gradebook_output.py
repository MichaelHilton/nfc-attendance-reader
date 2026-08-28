"""Phase 3 — output integrity, date filtering, reporting, and build() guards."""
import pytest

import build_gradebook as bg
import helpers

SESSION = bg.Session("2026-08-27", "10:00", 10.0, 30.0, 0.5, "Wk1 Activity")


def run(tmp_path, *, taps, registrations=None, aliases=None, students=None, session=SESSION):
    students = students or [("Chen, Alice", "alice@x.edu"), ("Diaz, Bob", "bob@x.edu")]
    registrations = registrations or {"0000000001": "Alice Chen", "0000000002": "Bob Diaz"}
    files = helpers.make_files(
        tmp_path,
        canvas=helpers.canvas_rows(students),
        registrations=registrations,
        taps=taps,
        aliases=aliases,
    )
    return files, bg.build(files["canvas"], files["attendance"], files["roster"],
                           files["aliases"], helpers.KAT_KEY, session)


# ------------------------------ output integrity ------------------------------
def test_only_target_column_changes_and_row_count_preserved(tmp_path):
    files, r = run(tmp_path, taps=[["2026-08-27 10:05:00", helpers.tok("0000000001")]])
    orig = helpers.canvas_rows([("Chen, Alice", "alice@x.edu"), ("Diaz, Bob", "bob@x.edu")])
    assert len(r.rows) == len(orig)
    target = len(helpers.CANVAS_HEADER) - 1
    for i in (2, 3):
        for c in range(len(orig[i])):
            if c != target:
                assert r.rows[i][c] == orig[i][c]      # identity columns untouched
    assert r.rows[2][target] == "2" and r.rows[3][target] == "0"


def test_every_student_row_padded_to_target_column(tmp_path):
    # Canvas rows that are SHORTER than the target column index.
    header = ["Student", "SIS Login ID", "A (1)", "B (1)", "Wk1 Activity (9)"]
    points = ["Points Possible", "", "1.00", "1.00", "2.00"]
    rows = [header, points,
            ["Chen, Alice", "alice@x.edu"],           # only 2 cells
            ["Diaz, Bob", "bob@x.edu", "", ""]]       # 4 cells
    files = helpers.make_files(
        tmp_path, canvas=rows,
        registrations={"0000000001": "Alice Chen"},
        taps=[["2026-08-27 10:05:00", helpers.tok("0000000001")]],
    )
    r = bg.build(files["canvas"], files["attendance"], files["roster"],
                 files["aliases"], helpers.KAT_KEY, SESSION)
    assert len(r.rows[2]) == 5 and r.rows[2][4] == "2"
    assert len(r.rows[3]) == 5 and r.rows[3][4] == "0"


def test_write_output_roundtrips(tmp_path):
    import csv
    files, r = run(tmp_path, taps=[["2026-08-27 10:05:00", helpers.tok("0000000001")]])
    out = tmp_path / "out.csv"
    bg.write_output(str(out), r.rows)
    assert list(csv.reader(open(out, newline=""))) == r.rows


# ------------------------------ date filtering ------------------------------
def test_unsynced_rows_counted_not_scored(tmp_path):
    files, r = run(tmp_path, taps=[
        ["2026-08-27 10:05:00", helpers.tok("0000000001")],
        ["unsynced-12345", helpers.tok("0000000002")],
    ])
    assert r.unsynced == 1
    assert (r.present, r.absent) == (1, 1)          # Bob only has the unsynced tap


def test_wrong_date_rows_ignored(tmp_path):
    files, r = run(tmp_path, taps=[
        ["2026-08-26 10:05:00", helpers.tok("0000000001")],   # day before
        ["2026-08-27 10:05:00", helpers.tok("0000000002")],
    ])
    assert (r.present, r.absent) == (1, 1)          # only Bob counted present


def test_malformed_timestamp_skipped(tmp_path):
    files, r = run(tmp_path, taps=[
        ["2026-08-27 10:05", helpers.tok("0000000001")],      # missing seconds
        ["2026-08-27 10:05:00", helpers.tok("0000000002")],
    ])
    assert (r.present, r.absent) == (1, 1)


# ------------------------------ reporting ------------------------------
def test_unregistered_card_reported(tmp_path):
    files, r = run(tmp_path, taps=[["2026-08-27 10:05:00", "deadbeef" * 4]])
    assert r.unregistered == ["deadbeef"]


def test_unmatched_name_reported(tmp_path):
    files, r = run(
        tmp_path,
        registrations={"0000000009": "Ghost Person"},
        taps=[["2026-08-27 10:05:00", helpers.tok("0000000009")]],
    )
    assert r.unmatched == ["Ghost Person"]


def test_ambiguous_name_reported(tmp_path):
    files, r = run(
        tmp_path,
        students=[("Smith, Pat", "p1@x.edu"), ("Smith, Pat", "p2@x.edu")],
        registrations={"0000000001": "Pat Smith"},
        taps=[["2026-08-27 10:05:00", helpers.tok("0000000001")]],
    )
    assert r.ambiguous == ["Pat Smith"]


def test_render_report_text(tmp_path):
    files, r = run(tmp_path, taps=[
        ["2026-08-27 10:05:00", helpers.tok("0000000001")],
        ["2026-08-27 10:20:00", helpers.tok("0000000002")],
    ])
    text = bg.render_report(r, SESSION, "out.csv")
    assert "Session 2026-08-27 10:00" in text
    assert "Result : 1 present, 1 late, 0 absent (of 2 enrolled)" in text
    assert "Column : Wk1 Activity (900001)   (present=2, late=1, absent=0)" in text
    assert text.rstrip().endswith("only 'Wk1 Activity (900001)' was changed)")


def test_render_report_all_warning_branches(tmp_path):
    files, r = run(
        tmp_path,
        students=[("Smith, Pat", "p1@x.edu"), ("Smith, Pat", "p2@x.edu"),
                  ("Chen, Alice", "alice@x.edu")],
        registrations={"0000000001": "Pat Smith", "0000000002": "Ghost Person",
                       "0000000003": "Alice Chen"},
        taps=[
            ["2026-08-27 10:05:00", helpers.tok("0000000001")],   # ambiguous
            ["2026-08-27 10:05:00", helpers.tok("0000000002")],   # unmatched
            ["2026-08-27 10:05:00", "deadbeef" * 4],              # unregistered
            ["unsynced-1", helpers.tok("0000000003")],            # unsynced
        ],
    )
    text = bg.render_report(r, SESSION, "out.csv")
    assert "1 tap(s) had no NTP time" in text
    assert '"Ghost Person",<their-sis-login-id' in text
    assert "matched more than one student" in text and "Pat Smith" in text
    assert "cards not in the roster (unregistered): deadbeef" in text


def test_blank_and_short_attendance_rows_are_skipped(tmp_path):
    files, r = run(tmp_path, taps=[
        [],
        ["only-one-field"],
        ["2026-08-27 10:05:00", helpers.tok("0000000001")],
    ])
    assert (r.present, r.absent) == (1, 1)


# ------------------------------ build() guards ------------------------------
def test_bad_date_exits(tmp_path):
    with pytest.raises(SystemExit):
        run(tmp_path, taps=[], session=bg.Session("27-08-2026", "10:00", 10, 30, 0.5, "Wk1 Activity"))


def test_missing_roster_exits(tmp_path):
    files = helpers.make_files(
        tmp_path, canvas=helpers.canvas_rows([("Chen, Alice", "a@x.edu")]),
        registrations={"0000000001": "Alice Chen"}, taps=[],
    )
    with pytest.raises(SystemExit):
        bg.build(files["canvas"], files["attendance"], str(tmp_path / "nope.csv"),
                 files["aliases"], helpers.KAT_KEY, SESSION)
