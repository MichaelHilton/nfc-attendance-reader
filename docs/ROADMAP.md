# Roadmap & Known Issues

Current status of the project: what's built and verified, what's still open, and
optional hardening someone could pick up. See `DESIGN_NOTES.md` §7 for the
reasoning behind the gradebook decisions.

---

## Done

- **Firmware — cloud removed, NTP added.**
  `attendance_reader_PN532.ino` no longer has the Google Apps Script upload. WiFi
  is used only to set the clock via `configTzTime` (US Eastern). Each tap logs a
  real local `timestamp,token`; before the clock syncs, rows are written
  `unsynced-<millis>` and the gradebook skips/flags them.
- **`software/build_gradebook.py` — written and verified.**
  Decrypts the roster, matches each AndrewID to Canvas by SIS Login ID local-part
  (alias first; then, for older name-based rosters, exact normalized and
  unique-subset for middle initials), scores
  Present/Late/Absent per session (`--date --start --late-after --close
  --late-frac --column`), absent = 0, and writes a Canvas-importable CSV plus a
  clear report of unmatched names, unregistered cards, and unsynced rows.
  Confirmed end-to-end against synthetic fixtures: every scoring tier, alias
  resolution, and each flag behaves correctly, and only the target column is
  changed. The firmware timestamp format and the gradebook parser agree exactly.
- **Secrets hygiene.**
  WiFi credentials *and* the crypto key are both out of the tracked sketch now.
  `wifi_config.h` and the new `secret_key.h` live beside the `.ino`, uncommitted,
  and are pulled in via `#if __has_include` with placeholder fallbacks so a
  fresh clone still compiles with neither present. `attendance_crypto.py` and
  `register_cards.py` write `secret_key.h` straight into the firmware folder —
  nothing gets hand-pasted into the sketch anymore. `.gitignore` covers
  `secret.key`, `wifi_config.h`, `secret_key.h`/`firmware_key.h`, real rosters/
  attendance logs/Canvas exports, and `software/.venv/`. `.example` templates
  (`wifi_config.h.example`, `aliases.csv.example`) ship so a clone is usable
  out of the box.

---

## Left to do

- **Rotate the real key before any classroom use.** The `SECRET_KEY` that was
  briefly hardcoded directly in the tracked `.ino` (before the `secret_key.h`
  fix above) should be treated as burned even though it was never actually
  pushed anywhere. Run `python3 software/attendance_crypto.py` to generate a
  fresh `secret.key`/`secret_key.h`, re-flash, confirm the boot self-test still
  prints `crypto self-test: HMAC OK, AES OK`, and re-register cards under the
  new key (a roster built under the old key won't match).
- **Put your real network in `wifi_config.h`.** It currently holds the home
  network; set whatever WiFi the reader will use in class (needed only so NTP can
  set the clock).

---

## Optional / nice-to-have

- **Harden the Canvas student-row detection.** `build_gradebook.py` identifies
  student rows by requiring an `@` in the SIS Login ID. If a real export ever puts
  a bare Andrew ID there (no `@`), it silently reports "0 enrolled" and marks
  everyone absent. Detecting the `Points Possible` row by its label instead would
  remove that assumption. (Not urgent — confirmed a non-issue for exports whose
  SIS Login ID is the full email.)
- **ESP32 flash-encryption + secure-boot.** The chosen threat model covers a lost
  SD card. Closing the "someone dumps the flash to extract the key" gap is a
  separate, larger effort, deferred by design (DESIGN_NOTES §6).

---

## Definition of done — met

- Device logs real local `timestamp,token`; no cloud code remains; boot self-test
  passes. ✓
- `build_gradebook.py` turns a day's log into a Canvas-importable CSV, scores
  Present/Late/Absent with absent = 0, and reports anything it couldn't place. ✓
- Verified end-to-end (synthetic). A real-card dry run with the rotated key is the
  last confirmation before relying on it in class.
