#!/usr/bin/env python3
"""
Decode an attendance log (tokens) back into names, using secret.key + roster.csv.

The device and cloud only ever store tokens. This runs on your laptop (which has
the key) to produce a readable attendance report. Nothing sensitive is created
until you run this, and it stays on your machine.

Inputs:
  attendance.csv  : rows of  millis,token   (from the SD card via sd_download.py,
                    or a Google-Sheet CSV export with a 'token' column)
  roster.csv      : rows of  token,encrypted_name   (from register_cards.py)
  secret.key      : the 32-byte key (hex)

Run:
    pip install cryptography
    python3 decode_attendance.py                       # attendance.csv + roster.csv here
    python3 decode_attendance.py class1.csv roster.csv
    python3 decode_attendance.py --out report.csv

Output columns:  raw_time, name        (unknown tokens -> "UNKNOWN <token[:8]>")
"""
import csv, os, sys, argparse
import attendance_crypto as ac


def token_to_name(K, roster_path):
    """Build {token: name} by decrypting the roster."""
    names = {}
    if not os.path.exists(roster_path):
        return names
    with open(roster_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or len(row[0].strip()) != 32:
                continue
            tok = row[0].strip()
            enc = row[1].strip() if len(row) > 1 else ""
            try:
                names[tok] = ac.decrypt_name(K, enc)
            except Exception:
                names[tok] = "(could not decrypt)"
    return names


def find_token_column(header):
    """Locate the token column in a header row (Google-Sheet export), else None."""
    for i, h in enumerate(header):
        if h.strip().lower() == "token":
            return i
    return None


def read_attendance(path):
    """Yield (time_field, token) from attendance.csv or a sheet export."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return
    header = rows[0]
    tok_col = find_token_column(header)
    if tok_col is not None:                       # sheet export with named columns
        time_col = 0 if tok_col != 0 else (1 if len(header) > 1 else 0)
        for r in rows[1:]:
            if len(r) > tok_col and len(r[tok_col].strip()) == 32:
                yield (r[time_col].strip() if len(r) > time_col else "", r[tok_col].strip())
        return
    # device format: millis,token  (skip a header row if present)
    for r in rows:
        if len(r) < 2:
            continue
        tok = r[1].strip()
        if len(tok) != 32:                        # header/blank
            continue
        yield (r[0].strip(), tok)


def decode(attendance_path, roster_path, K):
    """(rows_out, unknown_count, registered_count).

    rows_out is [[raw_time, name], ...]; tokens absent from the roster render as
    'UNKNOWN <token[:8]>'.
    """
    names = token_to_name(K, roster_path)
    rows_out, unknown = [], 0
    for t, tok in read_attendance(attendance_path):
        name = names.get(tok)
        if name is None:
            name = f"UNKNOWN {tok[:8]}"
            unknown += 1
        rows_out.append([t, name])
    return rows_out, unknown, len(names)


def write_report(path, rows_out):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["raw_time", "name"])
        w.writerows(rows_out)


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("attendance", nargs="?", default="attendance.csv")
    ap.add_argument("roster", nargs="?", default="roster.csv")
    ap.add_argument("--key", default="secret.key")
    ap.add_argument("--out", default="attendance_decoded.csv")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)

    if not os.path.exists(a.key):
        sys.exit(f"Missing {a.key} — this must be the SAME key used to build the roster.")
    if not os.path.exists(a.attendance):
        sys.exit(f"Missing {a.attendance}")
    K = ac.load_or_create_key(a.key)

    rows_out, unknown, registered = decode(a.attendance, a.roster, K)
    write_report(a.out, rows_out)

    print(f"Decoded {len(rows_out)} scans ({unknown} unknown) -> {a.out}")
    print(f"Roster had {registered} registered students.")


if __name__ == "__main__":
    main()
