#!/usr/bin/env python3
"""
Card registration station — builds an ENCRYPTED roster.csv for the reader.

A student taps their ID card on the USB reader, types their AndrewID, and it's saved.
The window matches the device screen (black; green = ready, cyan = saved).

Privacy: the card number is NEVER written to disk. roster.csv stores
    token,encrypted_name
where token = HMAC-SHA256(secret, id) and the name is AES-256 encrypted. Same
secret.key the firmware uses (see attendance_crypto.py). Reader = USB keyboard-wedge
(types the card number, e.g. 0984257796, + Enter).

First run creates secret.key and writes secret_key.h straight into the firmware
sketch folder (../firmware/attendance_reader_PN532/secret_key.h) — nothing to paste.

Run:
    pip install cryptography
    python3 register_cards.py                 # roster.csv + secret.key beside this script
    python3 register_cards.py myclass.csv     # custom roster file

Esc quits, F11 toggles full screen.
"""
import csv, os, sys, re
from datetime import datetime
import attendance_crypto as ac

# ----------------------------- roster core (testable) -----------------------------
ANDREW_ID_MIN, ANDREW_ID_MAX = 2, 8

def valid_andrew_id(s: str) -> bool:
    """An AndrewID is 2-8 characters long."""
    return ANDREW_ID_MIN <= len(s or "") <= ANDREW_ID_MAX

def looks_like_card_scan(s: str) -> bool:
    """True if s is a bare digit string -- what the reader types on a tap.

    A real AndrewID always has at least one letter. If the AndrewID prompt
    is on screen and the student taps their card again (e.g. the first tap
    "didn't seem to register"), the reader types the card number + Enter
    right into that box; without this check it gets saved as their AndrewID.
    """
    s = s or ""
    return s.isdigit()

def normalize_key(raw: str) -> str:
    """Whatever the reader typed -> the device's exact id format (10-digit decimal)."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    return f"{int(digits) % (1 << 32):010d}"

def load_roster(path: str) -> dict:
    """Return {token: encrypted_name}. Tolerates a header row and blank lines."""
    roster = {}
    if not os.path.exists(path):
        return roster
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row:
                continue
            tok = (row[0] or "").strip()
            if len(tok) != 32:                 # token is 32 hex chars; skips header/blank
                continue
            roster[tok] = row[1].strip() if len(row) > 1 else ""
    return roster

def save_roster(path: str, roster: dict) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["token", "enc"])
        for tok in sorted(roster):
            w.writerow([tok, roster[tok]])

def upsert(path: str, token: str, enc: str):
    """Add/replace one entry. Returns (('added'|'updated', prev_enc|None), count)."""
    roster = load_roster(path)
    prev = roster.get(token)
    roster[token] = enc
    save_roster(path, roster)
    return (("updated", prev) if prev is not None else ("added", None)), len(roster)


def registration_log_path(roster_path: str) -> str:
    return os.path.join(os.path.dirname(roster_path) or ".", "registration_log.csv")


def log_registration(log_path: str, token: str) -> None:
    """Append (timestamp, token) for a brand-new registration.

    roster.csv itself is a full rewrite on every save (sorted by token, no
    history), so without this there is no record of *when* a card was first
    registered -- which matters when registering stands in for a swipe.
    """
    is_new = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "token"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), token])

# ----------------------------------- GUI ------------------------------------------
def run_gui(path: str, key_path: str):
    import tkinter as tk

    fresh = not os.path.exists(key_path)
    K = ac.load_or_create_key(key_path)
    if fresh:
        fw_dir = os.path.join(os.path.dirname(key_path) or ".", "..",
                               "firmware", "attendance_reader_PN532")
        fw_key_path = os.path.join(fw_dir, "secret_key.h")
        if os.path.isdir(fw_dir):
            open(fw_key_path, "w").write(ac.firmware_key_snippet(K))
            print("\n*** A NEW secret key was created:", key_path)
            print("*** Wrote", fw_key_path, "- re-flash the sketch so the device picks it up.")
        else:
            print("\n*** A NEW secret key was created:", key_path)
            print("*** Run attendance_crypto.py to (re)write secret_key.h into the firmware folder.")
        print("*** Keep secret.key PRIVATE — never commit it or put it on the SD card.\n")

    BG, GREEN, CYAN, ORANGE, WHITE, GREY = "#000000","#28e04b","#25d7e0","#ff9a1f","#f2f2f2","#7d7d7d"
    root = tk.Tk(); root.title("Card Registration"); root.configure(bg=BG); root.geometry("900x560")
    try: root.attributes("-fullscreen", True)
    except tk.TclError: pass

    state = {"mode": "tap", "token": "", "reset_job": None}
    count = len(load_roster(path))

    big   = tk.Label(root, bg=BG, fg=GREEN, font=("Helvetica", 60, "bold"), wraplength=840, justify="center")
    small = tk.Label(root, bg=BG, fg=WHITE, font=("Helvetica", 26))
    entry = tk.Entry(root, bg="#111111", fg=WHITE, insertbackground=WHITE, font=("Helvetica", 40),
                     justify="center", relief="flat", highlightthickness=2,
                     highlightbackground=GREY, highlightcolor=CYAN)
    footer = tk.Label(root, bg=BG, fg=GREY, font=("Helvetica", 15))
    big.place(relx=0.5, rely=0.38, anchor="center")
    small.place(relx=0.5, rely=0.56, anchor="center")
    footer.place(relx=0.5, rely=0.95, anchor="center")

    def set_footer():
        footer.config(text=f"{count} registered   ·   {os.path.basename(path)}   ·   encrypted   ·   Esc to quit")

    def show(mode):
        state["mode"] = mode
        if state["reset_job"]:
            root.after_cancel(state["reset_job"]); state["reset_job"] = None
        if mode == "tap":
            state["token"] = ""
            big.config(text="Tap your card", fg=GREEN); small.config(text="hold it on the reader")
            entry.delete(0, tk.END); entry.place(relx=0.5, rely=1.5); entry.focus_set()   # off-screen capture
        elif mode == "andrewid":
            big.config(text="Type your AndrewID", fg=CYAN)
            small.config(text=f"{ANDREW_ID_MIN}-{ANDREW_ID_MAX} characters, then press Enter")
            entry.delete(0, tk.END); entry.place(relx=0.5, rely=0.70, anchor="center", relwidth=0.6); entry.focus_set()
        set_footer()

    def flash(msg, sub, color, ms=1800):
        big.config(text=msg, fg=color); small.config(text=sub)
        entry.place(relx=0.5, rely=1.5); state["mode"] = "flash"
        state["reset_job"] = root.after(ms, lambda: show("tap"))

    def on_return(_evt=None):
        raw = entry.get()
        if state["mode"] == "tap":
            cid = normalize_key(raw)
            if not cid or cid == "0000000000":
                flash("Read again", "card not recognized", ORANGE); return
            state["token"] = ac.token(K, cid)     # store the token, not the number
            existing = load_roster(path).get(state["token"])
            if existing is not None:
                try:
                    andrew_id = ac.decrypt_name(K, existing)
                except Exception:
                    andrew_id = ""
                flash("Registration complete", andrew_id or "card already registered", CYAN)
                return
            show("andrewid")
        elif state["mode"] == "andrewid":
            andrew_id = raw.strip()
            if looks_like_card_scan(andrew_id):
                entry.delete(0, tk.END)
                small.config(text="That's a card tap, not an AndrewID — type your AndrewID"); return
            if not valid_andrew_id(andrew_id):
                small.config(text=f"AndrewID must be {ANDREW_ID_MIN}-{ANDREW_ID_MAX} characters"); return
            enc = ac.encrypt_name(K, andrew_id)
            (action, prev), total = upsert(path, state["token"], enc)
            nonlocal count; count = total
            if action == "added":
                log_registration(registration_log_path(path), state["token"])
            if action == "updated" and prev:
                try: pn = ac.decrypt_name(K, prev)
                except Exception: pn = ""
                if pn and pn != andrew_id:
                    flash("Updated", f"{pn}  →  {andrew_id}", CYAN); return
            flash("Saved", andrew_id, CYAN)

    root.bind("<Return>", on_return); root.bind("<KP_Enter>", on_return)
    root.bind("<Escape>", lambda e: root.destroy())
    root.bind("<F11>", lambda e: root.attributes("-fullscreen", not root.attributes("-fullscreen")))
    show("tap"); root.mainloop()


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "roster.csv")
    run_gui(path, os.path.join(here, "secret.key"))
