"""Phase 3 — scoring tiers (build_gradebook.score_tap) and the earliest-tap /
best-status aggregation inside build()."""
import pytest

import build_gradebook as bg
import helpers

SESSION = bg.Session(date="2026-08-27", start="10:00",
                     late_after=10.0, close=30.0, late_frac=0.5, column="Wk1 Activity")


@pytest.mark.parametrize(
    "minutes, expected",
    [
        (-5.0, ("present", 2.0)),     # tapped before class start
        (0.0, ("present", 2.0)),
        (10.0, ("present", 2.0)),     # late_after boundary is inclusive
        (10.0001, ("late", 1.0)),
        (30.0, ("late", 1.0)),        # close boundary is inclusive
        (30.0001, ("absent", 0.0)),
        (999.0, ("absent", 0.0)),
    ],
)
def test_score_tap_tiers(minutes, expected):
    assert bg.score_tap(minutes, SESSION, full_pts=2.0, late_pts=1.0) == expected


def _run(tmp_path, taps, **session_kw):
    files = helpers.make_files(
        tmp_path,
        canvas=helpers.canvas_rows([
            ("Chen, Alice", "alice@x.edu"),
            ("Diaz, Bob", "bob@x.edu"),
        ]),
        registrations={"0000000001": "Alice Chen", "0000000002": "Bob Diaz"},
        taps=taps,
    )
    kw = dict(date="2026-08-27", start="10:00", late_after=10.0, close=30.0,
              late_frac=0.5, column="Wk1 Activity")
    kw.update(session_kw)
    return bg.build(files["canvas"], files["attendance"], files["roster"],
                    files["aliases"], helpers.KAT_KEY, bg.Session(**kw))


def test_present_late_absent_counts(tmp_path):
    r = _run(tmp_path, [
        ["2026-08-27 10:05:00", helpers.tok("0000000001")],   # present
        ["2026-08-27 10:20:00", helpers.tok("0000000002")],   # late
    ])
    assert (r.present, r.late, r.absent, r.enrolled) == (1, 1, 0, 2)


def test_never_tapped_student_is_absent_zero(tmp_path):
    r = _run(tmp_path, [["2026-08-27 10:05:00", helpers.tok("0000000001")]])
    assert (r.present, r.absent) == (1, 1)
    # Bob's row is index 3; trailing activity column filled with "0"
    assert r.rows[3][-1] == "0"


def test_earliest_tap_of_the_day_wins(tmp_path):
    r = _run(tmp_path, [
        ["2026-08-27 10:25:00", helpers.tok("0000000001")],   # later: would be late
        ["2026-08-27 10:02:00", helpers.tok("0000000001")],   # earlier: present
    ])
    assert (r.present, r.late) == (1, 0)


def test_late_value_uses_late_frac_of_points(tmp_path):
    r = _run(tmp_path,
             [["2026-08-27 10:20:00", helpers.tok("0000000001")]],
             late_frac=0.25)
    assert r.late_pts == 0.5                       # 2.00 * 0.25
    assert r.rows[2][-1] == "0.5"


def test_multiple_cards_one_student_keeps_best_status(tmp_path):
    # Two registered cards decrypt to the same typed name -> same Canvas row.
    files = helpers.make_files(
        tmp_path,
        canvas=helpers.canvas_rows([("Chen, Alice", "alice@x.edu")]),
        registrations={"0000000001": "Alice Chen", "0000000007": "Alice Chen"},
        taps=[
            ["2026-08-27 10:40:00", helpers.tok("0000000001")],   # absent-tier
            ["2026-08-27 10:05:00", helpers.tok("0000000007")],   # present-tier
        ],
    )
    r = bg.build(files["canvas"], files["attendance"], files["roster"],
                 files["aliases"], helpers.KAT_KEY,
                 bg.Session("2026-08-27", "10:00", 10.0, 30.0, 0.5, "Wk1 Activity"))
    assert (r.present, r.late, r.absent) == (1, 0, 0)
    assert r.rows[2][-1] == "2"
