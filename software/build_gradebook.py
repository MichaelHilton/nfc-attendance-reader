#!/usr/bin/env python3
"""
Fill a Canvas gradebook attendance column from the reader's SD log.

Runs on your laptop (which has secret.key). It decrypts each logged token -> the name
typed at registration, matches that name to a Canvas student, decides Present/Late/Absent
from the tap time, and writes a Canvas-importable CSV with just the one attendance column
filled. Absent = 0.

Inputs
  --canvas     Canvas gradebook export CSV (required)
  --attendance device log 'timestamp,token' (default attendance.csv)
  --roster     encrypted roster 'token,enc' (default roster.csv)
  --key        secret.key (default secret.key)
  --aliases    name fixups 'typed_name,sis_login_id' (default aliases.csv, optional)
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
"""
import csv, os, re, sys, argparse
from datetime import datetime, timedelta
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
    """{norm_tokens(typed_name): sis_login_lower}"""
    m = {}
    if path and os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row or len(row) < 2 or row[0].strip().lower() in ("", "typed_name"):
                    continue
                m[norm_tokens(row[0])] = row[1].strip().lower()
    return m


# ------------------------------- main ---------------------------------------
def main():
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
    a = ap.parse_args()

    for p in (a.key, a.canvas, a.attendance):
        if not os.path.exists(p):
            sys.exit(f"Missing {p}")
    K = ac.load_or_create_key(a.key)
    try:
        start_dt = datetime.strptime(f"{a.date} {a.start}", "%Y-%m-%d %H:%M")
    except ValueError:
        sys.exit("Bad --date/--start (want YYYY-MM-DD and HH:MM)")

    token_name = load_token_names(K, a.roster)
    aliases = load_aliases(a.aliases)

    # ---- parse the Canvas CSV ----
    with open(a.canvas, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) < 3:
        sys.exit("Canvas CSV looks empty.")
    header, points_row = rows[0], rows[1]

    def col_index(name):
        for i, h in enumerate(header):
            if h.strip().lower() == name.lower():
                return i
        sys.exit(f"Canvas CSV has no '{name}' column.")
    c_student, c_login = col_index("Student"), col_index("SIS Login ID")

    want = a.column.strip().lower()
    matches = [i for i, h in enumerate(header) if col_label(h) == want]
    if not matches:
        matches = [i for i, h in enumerate(header) if want in col_label(h)]
    if len(matches) == 0:
        sys.exit(f"No assignment column matches '{a.column}'.")
    if len(matches) > 1:
        opts = ", ".join(header[i] for i in matches)
        sys.exit(f"'{a.column}' is ambiguous; matches: {opts}")
    c_target = matches[0]

    try:
        full_pts = float(points_row[c_target])
    except (ValueError, IndexError):
        full_pts = 1.0
        print(f"! Could not read Points Possible for '{header[c_target]}'; assuming {full_pts}")
    late_pts = round(full_pts * a.late_frac, 4)

    # student rows = rows with an email in SIS Login ID
    student_rows = [i for i in range(2, len(rows))
                    if len(rows[i]) > c_login and "@" in rows[i][c_login]]
    by_login, by_norm = {}, {}
    for i in student_rows:
        by_login[rows[i][c_login].strip().lower()] = i
        by_norm.setdefault(norm_tokens(rows[i][c_student]), []).append(i)

    # ---- read attendance for the session date; earliest tap per token ----
    earliest, unsynced = {}, 0
    with open(a.attendance, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or len(row) < 2:
                continue
            ts, tok = row[0].strip(), row[1].strip()
            if len(tok) != 32:
                continue                      # header/blank
            if not ts.startswith(a.date):
                if ts.startswith("unsynced"):
                    unsynced += 1
                continue
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if tok not in earliest or dt < earliest[tok]:
                earliest[tok] = dt

    # ---- match each tap to a Canvas row + decide status ----
    def match_row(name):
        toks = norm_tokens(name)
        if toks in aliases and aliases[toks] in by_login:
            return by_login[aliases[toks]], "alias"
        if toks in by_norm and len(by_norm[toks]) == 1:
            return by_norm[toks][0], "exact"
        if toks in by_norm:
            return None, "ambiguous"
        cand = [i for i in student_rows
                if set(toks) and (set(toks) <= set(norm_tokens(rows[i][c_student]))
                                  or set(norm_tokens(rows[i][c_student])) <= set(toks))]
        if len(cand) == 1:
            return cand[0], "approx"
        return None, ("ambiguous" if cand else "none")

    row_status = {}          # canvas row idx -> ("present"|"late"|"absent", value)
    unregistered, unmatched, ambiguous = [], [], []
    for tok, dt in earliest.items():
        name = token_name.get(tok)
        if name is None:
            unregistered.append(tok[:8]); continue
        idx, how = match_row(name)
        if idx is None:
            (ambiguous if how == "ambiguous" else unmatched).append(name); continue
        mins = (dt - start_dt).total_seconds() / 60.0
        if mins <= a.late_after:
            st, val = "present", full_pts
        elif mins <= a.close:
            st, val = "late", late_pts
        else:
            st, val = "absent", 0.0          # arrived after attendance closed
        prev = row_status.get(idx)
        # if multiple cards map to one student, keep the best (earliest/highest) status
        rank = {"present": 3, "late": 2, "absent": 1}
        if prev is None or rank[st] > rank[prev[0]]:
            row_status[idx] = (st, val)

    # ---- fill the column: every student gets a value; absent = 0 ----
    present = late = absent = 0
    for i in student_rows:
        st, val = row_status.get(i, ("absent", 0.0))
        while len(rows[i]) <= c_target:
            rows[i].append("")
        rows[i][c_target] = fmt_points(val)
        present += st == "present"; late += st == "late"; absent += st == "absent"

    out = a.out or (os.path.splitext(a.canvas)[0] + "_filled.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    # ---- summary ----
    print(f"\nSession {a.date} {a.start}  (on-time <= {a.late_after:g} min, "
          f"late <= {a.close:g} min @ {a.late_frac:g}x)")
    print(f"Column : {header[c_target]}   (present={fmt_points(full_pts)}, "
          f"late={fmt_points(late_pts)}, absent=0)")
    print(f"Result : {present} present, {late} late, {absent} absent "
          f"(of {len(student_rows)} enrolled)")
    if unsynced:
        print(f"! {unsynced} tap(s) had no NTP time (logged 'unsynced') and were skipped.")
    if unmatched:
        print(f"! {len(unmatched)} tapped name(s) not found in Canvas -> add to {a.aliases}:")
        for n in sorted(set(unmatched)):
            print(f"    \"{n}\",<their-sis-login-id@your-school.edu>")
    if ambiguous:
        print(f"! {len(ambiguous)} tapped name(s) matched more than one student (fix via {a.aliases}): "
              + ", ".join(sorted(set(ambiguous))))
    if unregistered:
        print(f"! {len(unregistered)} tap(s) from cards not in the roster (unregistered): "
              + ", ".join(unregistered))
    print(f"\nWrote {out}  (import into Canvas; only '{header[c_target]}' was changed)")


if __name__ == "__main__":
    main()
