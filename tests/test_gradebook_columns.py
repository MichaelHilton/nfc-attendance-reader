"""Phase 3 — column resolution and Points Possible parsing."""
import pytest

import build_gradebook as bg
import helpers


def idx(header, points):
    return bg.build_index([header, points, ["Chen, Alice", "1", "u", "a@x.edu", "S", "1", ""]])


BASE_HEADER = ["Student", "ID", "SIS User ID", "SIS Login ID", "Root Account",
               "Section", "Aug 26 Activity (999001)", "Aug 27 Activity (999002)"]
BASE_POINTS = ["Points Possible", "", "", "", "", "", "1.00", "2.00"]


def test_exact_col_label_match_wins_over_substring():
    i = idx(BASE_HEADER, BASE_POINTS)
    # "aug 27 activity" is a substring of nothing else; exact label match resolves it
    assert bg.resolve_column(i, "Aug 27 Activity") == 7


def test_substring_fallback_when_no_exact_label():
    i = idx(BASE_HEADER, BASE_POINTS)
    assert bg.resolve_column(i, "Aug 27") == 7


def test_zero_matches_exits():
    i = idx(BASE_HEADER, BASE_POINTS)
    with pytest.raises(SystemExit):
        bg.resolve_column(i, "Nonexistent Column")


def test_ambiguous_substring_exits():
    i = idx(BASE_HEADER, BASE_POINTS)
    with pytest.raises(SystemExit):
        bg.resolve_column(i, "Activity")          # matches both Aug 26 and Aug 27


def test_points_possible_parsed():
    i = idx(BASE_HEADER, BASE_POINTS)
    full, warning = bg.points_for_column(i, 7)
    assert full == 2.0 and warning is None


def test_points_possible_missing_defaults_to_one_with_warning():
    header = ["Student", "SIS Login ID", "Wk1 (1)"]
    points = ["Points Possible", "", ""]          # blank cell
    i = bg.build_index([header, points, ["Chen, Alice", "a@x.edu", ""]])
    full, warning = bg.points_for_column(i, 2)
    assert full == 1.0
    assert warning.startswith("! Could not read Points Possible")


def test_points_possible_non_numeric_defaults_to_one():
    header = ["Student", "SIS Login ID", "Wk1 (1)"]
    points = ["Points Possible", "", "n/a"]
    i = bg.build_index([header, points, ["Chen, Alice", "a@x.edu", ""]])
    full, warning = bg.points_for_column(i, 2)
    assert full == 1.0 and warning is not None


def test_missing_student_column_exits():
    with pytest.raises(SystemExit):
        bg.build_index([["Name", "SIS Login ID", "Wk1"], ["Points Possible", "", ""],
                        ["x", "a@x.edu", ""]])


def test_canvas_csv_too_short_exits(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("Student,SIS Login ID\n")
    with pytest.raises(SystemExit):
        bg.parse_canvas(str(p))
