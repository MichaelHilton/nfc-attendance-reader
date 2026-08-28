"""Phase 3 — the thin CLI wrapper: parse_args / main / default_out_path."""
import pytest

import build_gradebook as bg
import helpers

KEY_HEX = helpers.KAT_KEY.hex()


def _files(tmp_path, **kw):
    kw.setdefault("canvas", helpers.canvas_rows([
        ("Chen, Alice", "alice@x.edu"), ("Diaz, Bob", "bob@x.edu")]))
    kw.setdefault("registrations", {"0000000001": "Alice Chen", "0000000002": "Bob Diaz"})
    kw.setdefault("taps", [
        ["2026-08-27 10:05:00", helpers.tok("0000000001")],
        ["2026-08-27 10:20:00", helpers.tok("0000000002")],
    ])
    f = helpers.make_files(tmp_path, **kw)
    (tmp_path / "secret.key").write_text(KEY_HEX)
    f["key"] = str(tmp_path / "secret.key")
    return f


def _argv(f, tmp_path, *, column="Wk1 Activity", extra=()):
    return [
        "--canvas", f["canvas"], "--attendance", f["attendance"],
        "--roster", f["roster"], "--key", f["key"], "--aliases", f["aliases"],
        "--date", "2026-08-27", "--start", "10:00", "--column", column,
        "--out", str(tmp_path / "out.csv"), *extra,
    ]


def test_default_out_path():
    assert bg.default_out_path("/x/Grades.csv") == "/x/Grades_filled.csv"


def test_parse_args_defaults():
    a = bg.parse_args(["--canvas", "c", "--date", "d", "--start", "s", "--column", "col"])
    assert (a.attendance, a.roster, a.key, a.aliases) == (
        "attendance.csv", "roster.csv", "secret.key", "aliases.csv")
    assert (a.late_after, a.close, a.late_frac) == (10.0, 30.0, 0.5)


def test_main_happy_path_writes_file_and_prints_report(tmp_path, capsys):
    f = _files(tmp_path)
    bg.main(_argv(f, tmp_path))
    out = capsys.readouterr().out
    assert "Result : 1 present, 1 late, 0 absent (of 2 enrolled)" in out
    assert (tmp_path / "out.csv").exists()
    written = (tmp_path / "out.csv").read_text().splitlines()
    assert written[0].startswith("Student,")
    assert written[2].endswith(",2")          # Alice present -> 2.00
    assert written[3].endswith(",1")          # Bob late -> 1.00


def test_main_prints_points_possible_warning(tmp_path, capsys):
    canvas = helpers.canvas_rows(
        [("Chen, Alice", "alice@x.edu")],
        points=["Points Possible", "", "", "", "", "", ""],   # blank -> warning
    )
    f = _files(tmp_path, canvas=canvas,
               registrations={"0000000001": "Alice Chen"},
               taps=[["2026-08-27 10:05:00", helpers.tok("0000000001")]])
    bg.main(_argv(f, tmp_path))
    out = capsys.readouterr().out
    assert "! Could not read Points Possible" in out
    assert "assuming 1.0" in out


def test_main_missing_input_file_exits(tmp_path):
    f = _files(tmp_path)
    f["canvas"] = str(tmp_path / "gone.csv")
    with pytest.raises(SystemExit):
        bg.main(_argv(f, tmp_path))


def test_main_out_defaults_next_to_canvas(tmp_path, capsys):
    f = _files(tmp_path)
    argv = [
        "--canvas", f["canvas"], "--attendance", f["attendance"],
        "--roster", f["roster"], "--key", f["key"], "--aliases", f["aliases"],
        "--date", "2026-08-27", "--start", "10:00", "--column", "Wk1 Activity",
    ]
    bg.main(argv)
    assert bg.default_out_path(f["canvas"]).endswith("canvas_filled.csv")
    assert (tmp_path / "canvas_filled.csv").exists()
