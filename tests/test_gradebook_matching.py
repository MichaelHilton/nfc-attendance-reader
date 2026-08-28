"""Phase 3 — the name-matching algorithm (build_gradebook.match_row).

match_row was lifted out of main() to module scope taking a CanvasIndex; these
tests build a tiny index and exercise every branch.
"""
import build_gradebook as bg
import helpers


def idx(*students):
    """students: (display_name, sis_login_id). Row indices start at 2."""
    return bg.build_index(helpers.canvas_rows(students))


def test_alias_resolves_to_sis_login():
    i = idx(("Chen, Alice", "alice@x.edu"), ("Diaz, Bob", "bob@x.edu"))
    aliases = {bg.norm_tokens("Mike Chen"): "alice@x.edu"}
    assert bg.match_row(i, "Mike Chen", aliases) == (2, "alias")


def test_alias_target_not_enrolled_falls_through_to_none():
    i = idx(("Chen, Alice", "alice@x.edu"))
    aliases = {bg.norm_tokens("Mike Chen"): "ghost@x.edu"}
    assert bg.match_row(i, "Mike Chen", aliases) == (None, "none")


def test_exact_unique_normalized_match():
    i = idx(("Chen, Alice", "a@x.edu"), ("Diaz, Bob", "b@x.edu"))
    assert bg.match_row(i, "alice   chen", {}) == (2, "exact")


def test_exact_but_two_students_same_name_is_ambiguous():
    i = idx(("Smith, Pat", "p1@x.edu"), ("Smith, Pat", "p2@x.edu"))
    assert bg.match_row(i, "Pat Smith", {}) == (None, "ambiguous")


def test_subset_match_handles_middle_initial():
    i = idx(("Nguyen, David M", "d@x.edu"))
    assert bg.match_row(i, "David Nguyen", {}) == (2, "approx")


def test_superset_match_when_tap_has_the_extra_token():
    i = idx(("Lee, Sam", "s@x.edu"))
    assert bg.match_row(i, "Sam K Lee", {}) == (2, "approx")


def test_approx_with_multiple_candidates_is_ambiguous():
    i = idx(("Lee, Sam Jr", "a@x.edu"), ("Lee, Sam II", "b@x.edu"))
    assert bg.match_row(i, "Sam Lee", {}) == (None, "ambiguous")


def test_no_candidate_at_all_is_none():
    i = idx(("Chen, Alice", "a@x.edu"))
    assert bg.match_row(i, "Bob Jones", {}) == (None, "none")


def test_empty_name_never_matches_by_subset():
    i = idx(("Chen, Alice", "a@x.edu"))
    assert bg.match_row(i, "", {}) == (None, "none")


def test_alias_checked_before_exact():
    # Tap name matches one student exactly, but an alias points elsewhere: alias wins.
    i = idx(("Chen, Alice", "alice@x.edu"), ("Diaz, Bob", "bob@x.edu"))
    aliases = {bg.norm_tokens("Alice Chen"): "bob@x.edu"}
    assert bg.match_row(i, "Alice Chen", aliases) == (3, "alias")
