#!/usr/bin/env python3
"""
Recover real calendar dates for a device attendance.csv whose clock never
synced (WiFi/NTP failed after setup), so every tap was logged as
'unsynced-<millis-since-boot>' instead of a timestamp.

A "session" = one power-on run of the reader: a boot resets millis to ~0 and
drops the synced clock, so a session boundary is either millis going backwards
or the log flipping from a real timestamp back to 'unsynced-N'. This script
finds those boundaries, then applies a session-number -> date mapping you
supply (figured out by hand from session size / which students appear /
nearby synced timestamps -- see `sessionize` output).

Within a mapped session, each tap's time-of-day is reconstructed as the
elapsed time since that session's FIRST tap (00:00:00 = first tap). That
assumes the reader was powered on at/near class start, which matched the
evidence on the one day we could verify (2026-08-28: the reboot that started
the real class session landed within ~5 min of the last synced timestamp).
Run build_gradebook.py against the output with --start 00:00 for these
recovered dates; the late/absent minute math still works because it's all
relative to session start.

Usage:
    python3 recover_sessions.py attendance.csv \
        --map 5=2026-08-28 --map 7=2026-09-08 --map 8=2026-09-10 \
        --out attendance_recovered.csv
"""
import csv, os, re, sys, argparse
from datetime import datetime, timedelta

import attendance_crypto as ac

_TS_RE = re.compile(r"^(unsynced-\d+|\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$")


def read_rows(path):
    """Yield (lineno, ts, tok) for real device-format rows (32-char token).
    A too-short token (truncated by a bad SD read) is reported, not yielded.
    A garbled timestamp (e.g. NUL-padded by a torn SD write) is reported and
    dropped too -- letting it through as-is would misclassify it as a 'synced'
    row (it doesn't start with 'unsynced-') and falsely split the session it
    landed in."""
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.reader(f), start=1):
            if len(row) != 2:                  # 3-col rows are the pre-roster test format; skip quietly
                continue
            ts, tok = row[0].strip(), row[1].strip()
            if not tok:
                continue
            if len(tok) != 32:
                print(f"  ! line {i}: truncated token ({len(tok)} of 32 chars), dropped: {ts},{tok}",
                      file=sys.stderr)
                continue
            if not _TS_RE.match(ts):
                print(f"  ! line {i}: garbled timestamp, dropped: {ts[:20]!r}...,{tok}",
                      file=sys.stderr)
                continue
            yield i, ts, tok


def sessionize(rows):
    sessions = []
    cur = []
    prev_kind = prev_millis = None
    for lineno, ts, tok in rows:
        if ts.startswith("unsynced-"):
            try:
                m = int(ts.split("-", 1)[1])
            except ValueError:
                m = None
            kind = "unsynced"
        else:
            m, kind = None, "synced"

        boundary = (
            not cur
            or (prev_kind == "synced" and kind == "unsynced")
            or (prev_kind == "unsynced" and kind == "unsynced"
                and m is not None and prev_millis is not None and m < prev_millis)
        )
        if boundary and cur:
            sessions.append(cur)
            cur = []
        cur.append((lineno, ts, tok, kind, m))
        prev_kind, prev_millis = kind, (m if kind == "unsynced" else None)
    if cur:
        sessions.append(cur)
    return sessions


def parse_map(pairs):
    out = {}
    for p in pairs:
        idx, date = p.split("=", 1)
        datetime.strptime(date, "%Y-%m-%d")   # validate
        out[int(idx)] = date
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("attendance")
    ap.add_argument("--map", action="append", default=[],
                     help="session_number=YYYY-MM-DD, repeatable")
    ap.add_argument("--out", default="attendance_recovered.csv")
    ap.add_argument("--roster", default="roster.csv")
    ap.add_argument("--key", default="secret.key")
    a = ap.parse_args(argv)

    session_dates = parse_map(a.map)
    rows = list(read_rows(a.attendance))
    sessions = sessionize(rows)

    K = ac.load_or_create_key(a.key)
    names = {}
    if os.path.exists(a.roster):
        with open(a.roster, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row or len(row[0].strip()) != 32:
                    continue
                tok = row[0].strip()
                enc = row[1].strip() if len(row) > 1 else ""
                try:
                    names[tok] = ac.decrypt_name(K, enc)
                except Exception:
                    names[tok] = "(could not decrypt)"

    out_rows = []          # (timestamp, token) in original device format
    per_day = {}           # date -> sorted set of names

    for i, sess in enumerate(sessions, start=1):
        date = session_dates.get(i)
        if date is None:
            for lineno, ts, tok, kind, m in sess:
                if kind == "synced":
                    out_rows.append((ts, tok))          # keep real synced rows as-is
            continue

        unsynced_millis = [m for _, _, _, kind, m in sess if kind == "unsynced" and m is not None]
        t0 = min(unsynced_millis) if unsynced_millis else 0
        attendees = per_day.setdefault(date, set())
        for lineno, ts, tok, kind, m in sess:
            if kind == "synced":
                out_rows.append((ts, tok))
                continue
            offset = timedelta(milliseconds=(m - t0))
            synth = f"{date} {(datetime.min + offset).strftime('%H:%M:%S')}"
            out_rows.append((synth, tok))
            attendees.add(names.get(tok, f"UNREGISTERED {tok[:8]}"))

    out_rows.sort(key=lambda r: r[0])
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "token"])
        w.writerows(out_rows)

    print(f"Wrote {a.out} ({len(out_rows)} rows)\n")
    for date in sorted(per_day):
        who = sorted(per_day[date])
        print(f"=== {date}  ({len(who)} present) ===")
        print(", ".join(who))
        print()


if __name__ == "__main__":
    main()
