#!/usr/bin/env python3
"""
Fill a Canvas gradebook attendance column from the reader's SD log.

Runs on your laptop (which has secret.key). It decrypts each logged token -> the AndrewID
typed at registration, matches that AndrewID to a Canvas student by SIS Login ID, decides
Present/Late/Absent from the tap time, and writes a Canvas-importable CSV with just the one
attendance column filled. Absent = 0.

Older rosters that stored a typed name still work: matching falls back to name
comparison (and the --aliases file) when a value isn't an AndrewID.

Inputs
  --canvas     Canvas gradebook export CSV (required)
  --attendance device log 'timestamp,token' (default attendance.csv)
  --roster     encrypted roster 'token,enc' (default roster.csv)
  --key        secret.key (default secret.key)
  --aliases    name/ID fixups 'typed_value,sis_login_id' (default aliases.csv, optional)
Session
  --date       session date YYYY-MM-DD (required)
  --start      class start HH:MM 24h (required)
  --late-after minutes after start still counted on-time  (default 10)
  --close      minutes after start after which it's absent (default 30)
  --late-frac  fraction of points for a late tap          (default 0.5)
  --column     Canvas assignment column to fill, e.g. "Aug 25 Activity" (required)
  --out        output CSV (default <canvas>_filled.csv)

Requires:  pip install cryptography
Example:
  python3 build_gradebook.py --canvas Grades.csv --attendance att.csv \
      --date 2026-08-25 --start 10:00 --late-after 10 --close 30 \
      --late-frac 0.5 --column "Aug 25 Activity"

Structure: parse_args() -> build() -> Result; render_report() + write_output().
build() does all the file reading and the matching/scoring; it raises SystemExit
on bad input (missing files, unusable Canvas CSV, unresolvable --column) exactly
as the script always has. main() is the thin CLI wrapper.
"""
import csv, os, re, sys, argparse
from dataclasses import dataclass, field
from datetime import datetime

import attendance_crypto as ac


# ------------------------------- helpers ------------------------------------
def norm_tokens(s):
    """Canonical name form: lowercase alpha/num tokens, sorted (order-independent)."""
    s = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return tuple(sorted(t for t in s.split() if t))


def fmt_points(x):
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return ("%.4f" % x).rstrip("0").rstrip(".")


def col_label(h):
    """Header 'Jan 20 Activity (995978)' -> 'jan 20 activity' for matching."""
    return re.sub(r"\s*\(\d+\)\s*$", "", h or "").strip().lower()


def load_token_names(K, roster_path):
    names = {}
    if not os.path.exists(roster_path):
        sys.exit(f"Missing {roster_path}")
    with open(roster_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or len(row[0].strip()) != 32:
                continue
            try:
                names[row[0].strip()] = ac.decrypt_name(K, row[1].strip())
            except Exception:
                names[row[0].strip()] = "(decrypt failed)"
    return names


def load_aliases(path):
    """{norm_tokens(typed_value): sis_login_lower}"""
    m = {}
    if path and os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row or len(row) < 2 or row[0].strip().lower() in ("", "typed_name", "typed_value"):
                    continue
                m[norm_tokens(row[0])] = row[1].strip().lower()
    return m


# --------------------------- Canvas CSV parsing ---------------------------
@dataclass
class CanvasIndex:
    """A parsed Canvas export: the raw rows plus the lookups build() needs."""
    header: list
    points_row: list
    rows: list                       # every row of the CSV, mutated in place on fill
    c_student: int
    c_login: int
    student_rows: list               # row indices that look like enrolled students
    by_login: dict                   # sis_login_lower -> row index
    by_andrew: dict                  # andrew_id_lower (SIS login local-part) -> [row indices]
    by_norm: dict                    # norm_tokens(student name) -> [row indices]


def parse_canvas(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) < 3:
        sys.exit("Canvas CSV looks empty.")
    return rows


def _canvas_col_index(header, name):
    for i, h in enumerate(header):
        if h.strip().lower() == name.lower():
            return i
    sys.exit(f"Canvas CSV has no '{name}' column.")


def build_index(rows):
    header, points_row = rows[0], rows[1]
    c_student = _canvas_col_index(header, "Student")
    c_login = _canvas_col_index(header, "SIS Login ID")

    # student rows = rows with an email in SIS Login ID
    student_rows = [i for i in range(2, len(rows))
                    if len(rows[i]) > c_login and "@" in rows[i][c_login]]
    by_login, by_andrew, by_norm = {}, {}, {}
    for i in student_rows:
        login = rows[i][c_login].strip().lower()
        by_login[login] = i
        local = login.split("@", 1)[0]
        if local:
            by_andrew.setdefault(local, []).append(i)
        by_norm.setdefault(norm_tokens(rows[i][c_student]), []).append(i)
    return CanvasIndex(header, points_row, rows, c_student, c_login,
                       student_rows, by_login, by_andrew, by_norm)


def resolve_column(index, column):
    """Return the target column index for --column, or SystemExit if it can't."""
    want = column.strip().lower()
    matches = [i for i, h in enumerate(index.header) if col_label(h) == want]
    if not matches:
        matches = [i for i, h in enumerate(index.header) if want in col_label(h)]
    if len(matches) == 0:
        sys.exit(f"No assignment column matches '{column}'.")
    if len(matches) > 1:
        opts = ", ".join(index.header[i] for i in matches)
        sys.exit(f"'{column}' is ambiguous; matches: {opts}")
    return matches[0]


def points_for_column(index, c_target):
    """(full_points, warning_or_None) from the Points Possible row."""
    try:
        return float(index.points_row[c_target]), None
    except (ValueError, IndexError):
        full = 1.0
        return full, (f"! Could not read Points Possible for "
                      f"'{index.header[c_target]}'; assuming {full}")


# ---------------------------- attendance log ----------------------------
def read_earliest_taps(path, date):
    """{token: earliest datetime on `date`}, count of 'unsynced' rows."""
    earliest, unsynced = {}, 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or len(row) < 2:
                continue
            ts, tok = row[0].strip(), row[1].strip()
            if len(tok) != 32:
                continue                      # header/blank
            if not ts.startswith(date):
                if ts.startswith("unsynced"):
                    unsynced += 1
                continue
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if tok not in earliest or dt < earliest[tok]:
                earliest[tok] = dt
    return earliest, unsynced


# ------------------------------- matching ------------------------------
def match_row(index, value, aliases):
    """Map a tapped value (an AndrewID, or a typed name from an older roster) to a
    Canvas row index.

    Returns (row_index, how) where how is one of
    'alias' | 'andrewid' | 'exact' | 'approx', or (None, how) with how in
    'ambiguous' | 'none'.
    """
    toks = norm_tokens(value)
    if toks in aliases and aliases[toks] in index.by_login:
        return index.by_login[aliases[toks]], "alias"
    aid = (value or "").strip().lower()
    if aid in index.by_andrew:
        hits = index.by_andrew[aid]
        return (hits[0], "andrewid") if len(hits) == 1 else (None, "ambiguous")
    if toks in index.by_norm and len(index.by_norm[toks]) == 1:
        return index.by_norm[toks][0], "exact"
    if toks in index.by_norm:
        return None, "ambiguous"
    cand = [i for i in index.student_rows
            if set(toks) and (set(toks) <= set(norm_tokens(index.rows[i][index.c_student]))
                              or set(norm_tokens(index.rows[i][index.c_student])) <= set(toks))]
    if len(cand) == 1:
        return cand[0], "approx"
    return None, ("ambiguous" if cand else "none")


_RANK = {"present": 3, "late": 2, "absent": 1}


def score_tap(minutes_late, session, full_pts, late_pts):
    """(status, value) for a tap `minutes_late` minutes after class start."""
    if minutes_late <= session.late_after:
        return "present", full_pts
    if minutes_late <= session.close:
        return "late", late_pts
    return "absent", 0.0                       # arrived after attendance closed


# ------------------------------- session / result -------------------------
@dataclass
class Session:
    date: str
    start: str
    late_after: float
    close: float
    late_frac: float
    column: str


@dataclass
class Result:
    rows: list                 # full Canvas rows, target column filled
    target_header: str
    full_pts: float
    late_pts: float
    present: int
    late: int
    absent: int
    enrolled: int
    unsynced: int
    aliases_path: str
    unmatched: list = field(default_factory=list)
    ambiguous: list = field(default_factory=list)
    unregistered: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# --------------------------------- build --------------------------------
def build(canvas_path, attendance_path, roster_path, aliases_path, K, session):
    """Do everything except argument parsing and printing. Raises SystemExit on
    bad input, exactly as the script always has."""
    try:
        start_dt = datetime.strptime(f"{session.date} {session.start}", "%Y-%m-%d %H:%M")
    except ValueError:
        sys.exit("Bad --date/--start (want YYYY-MM-DD and HH:MM)")

    token_id = load_token_names(K, roster_path)
    aliases = load_aliases(aliases_path)

    index = build_index(parse_canvas(canvas_path))
    c_target = resolve_column(index, session.column)
    full_pts, warning = points_for_column(index, c_target)
    late_pts = round(full_pts * session.late_frac, 4)

    earliest, unsynced = read_earliest_taps(attendance_path, session.date)

    row_status = {}          # canvas row idx -> ("present"|"late"|"absent", value)
    unregistered, unmatched, ambiguous = [], [], []
    for tok, dt in earliest.items():
        who = token_id.get(tok)
        if who is None:
            unregistered.append(tok[:8]); continue
        idx, how = match_row(index, who, aliases)
        if idx is None:
            (ambiguous if how == "ambiguous" else unmatched).append(who); continue
        mins = (dt - start_dt).total_seconds() / 60.0
        st, val = score_tap(mins, session, full_pts, late_pts)
        prev = row_status.get(idx)
        # if multiple cards map to one student, keep the best (earliest/highest) status
        if prev is None or _RANK[st] > _RANK[prev[0]]:
            row_status[idx] = (st, val)

    # ---- fill the column: every student gets a value; absent = 0 ----
    present = late = absent = 0
    for i in index.student_rows:
        st, val = row_status.get(i, ("absent", 0.0))
        while len(index.rows[i]) <= c_target:
            index.rows[i].append("")
        index.rows[i][c_target] = fmt_points(val)
        present += st == "present"; late += st == "late"; absent += st == "absent"

    return Result(
        rows=index.rows,
        target_header=index.header[c_target],
        full_pts=full_pts,
        late_pts=late_pts,
        present=present, late=late, absent=absent,
        enrolled=len(index.student_rows),
        unsynced=unsynced,
        aliases_path=aliases_path,
        unmatched=unmatched, ambiguous=ambiguous, unregistered=unregistered,
        warnings=[warning] if warning else [],
    )


# ------------------------------ output ---------------------------------
def default_out_path(canvas_path):
    return os.path.splitext(canvas_path)[0] + "_filled.csv"


def write_output(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def render_report(result, session, out_path):
    r, s = result, session
    lines = [
        f"\nSession {s.date} {s.start}  (on-time <= {s.late_after:g} min, "
        f"late <= {s.close:g} min @ {s.late_frac:g}x)",
        f"Column : {r.target_header}   (present={fmt_points(r.full_pts)}, "
        f"late={fmt_points(r.late_pts)}, absent=0)",
        f"Result : {r.present} present, {r.late} late, {r.absent} absent "
        f"(of {r.enrolled} enrolled)",
    ]
    if r.unsynced:
        lines.append(f"! {r.unsynced} tap(s) had no NTP time (logged 'unsynced') and were skipped.")
    if r.unmatched:
        lines.append(f"! {len(r.unmatched)} tapped ID(s) not found in Canvas -> add to {r.aliases_path}:")
        for n in sorted(set(r.unmatched)):
            lines.append(f"    \"{n}\",<their-sis-login-id@your-school.edu>")
    if r.ambiguous:
        lines.append(f"! {len(r.ambiguous)} tapped ID(s) matched more than one student "
                     f"(fix via {r.aliases_path}): " + ", ".join(sorted(set(r.ambiguous))))
    if r.unregistered:
        lines.append(f"! {len(r.unregistered)} tap(s) from cards not in the roster (unregistered): "
                     + ", ".join(r.unregistered))
    lines.append(f"\nWrote {out_path}  (import into Canvas; only '{r.target_header}' was changed)")
    return "\n".join(lines)


# --------------------------------- main ---------------------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--canvas", required=True)
    ap.add_argument("--attendance", default="attendance.csv")
    ap.add_argument("--roster", default="roster.csv")
    ap.add_argument("--key", default="secret.key")
    ap.add_argument("--aliases", default="aliases.csv")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--start", required=True, help="HH:MM (24h)")
    ap.add_argument("--late-after", type=float, default=10.0)
    ap.add_argument("--close", type=float, default=30.0)
    ap.add_argument("--late-frac", type=float, default=0.5)
    ap.add_argument("--column", required=True)
    ap.add_argument("--out")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)

    for p in (a.key, a.canvas, a.attendance):
        if not os.path.exists(p):
            sys.exit(f"Missing {p}")
    K = ac.load_or_create_key(a.key)
    session = Session(a.date, a.start, a.late_after, a.close, a.late_frac, a.column)

    result = build(a.canvas, a.attendance, a.roster, a.aliases, K, session)
    for w in result.warnings:
        print(w)

    out = a.out or default_out_path(a.canvas)
    write_output(out, result.rows)
    print(render_report(result, session, out))


if __name__ == "__main__":
    main()
