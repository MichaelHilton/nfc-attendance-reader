# NFC Attendance Reader

A classroom attendance reader: students tap their 13.56 MHz university ID card on a
desktop device, which shows their name, beeps, and logs attendance to an SD card.
Registration and grading happen on the instructor's laptop. Card numbers are never
stored in plain text, and there's no cloud service involved -- everything stays on
the device's SD card and your laptop.

Built for a Canvas classroom, but the pieces are separable: the reader/registration
system has no LMS dependency, and only `software/build_gradebook.py` knows about
Canvas specifically (see `docs/DESIGN_NOTES.md` Section 7).

## Hardware
- **ESP32-3248S035C** ("Cheap Yellow Display" / CYD, 3.5" ST7796 screen, WiFi, SD)
- **PN532** NFC reader over I2C (CN1: 3V3, GND, SDA=IO21, SCL=IO22; DIP switches = I2C)
- 20 mm speaker on the SPEAK connector (GPIO26)
- LiPo battery + USB-C charge/boost module (V713), power switch, all in a 3D-printed case
- Registration reader (laptop): a USB keyboard-wedge NFC reader that types the card number

## Folder layout
- **case/** — 3D-printable enclosure
  - `case_body.stl`, `case_lid.stl`, `case_stand.stl` — print these (PLA/PETG, 0.2 mm, no supports)
  - `case_gen.py` — parametric source (all dimensions at the top; regenerates the STLs)
  - `case_notes.md` — assembly, wiring, print settings, and every adjustable parameter
- **firmware/** — Arduino sketches for the CYD
  - `attendance_reader_PN532/` — the main sketch (open this folder in Arduino IDE)
  - `diagnostics/` — `i2c_scan`, `pn532_test`, `speaker_test` for bring-up/troubleshooting
  - `setup-arduino.sh` / `flash.sh` — install arduino-cli + the ESP32 core, then compile/flash from the command line
- **software/** — laptop-side Python (needs `pip install cryptography pyserial`)
  - `attendance_crypto.py` — shared crypto (keys, tokens, name encryption)
  - `register_cards.py` — registration station GUI → builds encrypted `roster.csv`, and appends each new card to `registration_log.csv`
  - `decode_attendance.py` — turns logged tokens back into AndrewIDs
  - `build_gradebook.py` — fills a Canvas attendance column (Present/Late/Absent) from the log
  - `recover_sessions.py` — dates the `unsynced-<millis>` rows of a log whose clock never synced
  - `reader_test.py` — shows exactly what the USB registration reader types
  - `sd_download.py` — pulls `attendance.csv`/`roster.csv` off the device over USB serial
  - `sd_upload.py` — pushes a new `roster.csv` to the device over USB serial (no SD card removal)
  - `aliases.csv` (copy from `aliases.csv.example`) — `typed_value,sis_login_id` fixups for AndrewIDs/names that don't match Canvas
  - `serial_bridge_host.sh` / `serial_bridge.sh` — bridge the board's USB serial port into the dev container (`SERIAL_BRIDGE.md`)

## How the pieces fit
1. **Generate the key (once):** `python3 software/attendance_crypto.py` → creates
   `secret.key` (keep private!) and writes `secret_key.h` straight into
   `firmware/attendance_reader_PN532/` — nothing to paste, and it's gitignored.
2. **Flash the device:** copy `wifi_config.h.example` to `wifi_config.h` in that same
   folder and fill in your network, then upload the sketch. The Serial Monitor should
   print `crypto self-test: HMAC OK, AES OK`.
3. **Register students:** `python3 software/register_cards.py` — each student taps and
   types their AndrewID (2-8 characters) → writes `roster.csv` (only `token,encrypted_name`)
   and logs when each new card was registered in `registration_log.csv`. Get it onto the
   device either by copying the file to the SD card, or — with the device still plugged
   in — `python3 software/sd_upload.py roster.csv` (sends it over USB; the device swaps
   it in and reloads without a reboot).
4. **In class:** the device reads cards, shows the AndrewID, logs `timestamp,token` to the SD
   (WiFi sets the clock over NTP; no cloud).
5. **Grade:** pull the log with `sd_download.py`, then run `build_gradebook.py` with the
   session date/time and the Canvas column to fill — it matches each AndrewID to a Canvas
   student by SIS Login ID and writes a Canvas-importable CSV (Present/Late/Absent,
   absent = 0). Students who registered a card that day but never tapped are credited
   from their registration time. `decode_attendance.py` gives a plain AndrewID+times list
   if you just want to read the log. If the clock never synced (every row
   `unsynced-…`), date the rows first with `recover_sessions.py` (TESTING_GUIDE Step 7).

Example gradebook run:
```
python3 software/build_gradebook.py --canvas Grades.csv --attendance attendance.csv \
    --date 2026-08-25 --start 10:00 --late-after 10 --close 30 --late-frac 0.5 \
    --column "Aug 25 Activity"
```
AndrewIDs match Canvas students by SIS Login ID. Anything that still doesn't match
is reported; pin it once in `aliases.csv` (`typed_value,sis_login_id`) and re-run.

## Dev container vs. host
The repo ships a dev container with the Python deps, arduino-cli and a browser
desktop (noVNC on forwarded port **6080**, password `vscode`) for running
`register_cards.py`. The container **can't see USB**, so flashing and the serial
tools (`sd_download.py`, `sd_upload.py`, `reader_test.py`) run on the host in a
virtualenv at `software/path/to/venv`, or go through the TCP serial bridge in
`software/SERIAL_BRIDGE.md`. Setup and a full "where does each command run" table
are in `docs/TESTING_GUIDE.md` Step 0.

## Security model
- Card numbers are **never** written to disk — only `token = HMAC-SHA256(key, id)`.
- The AndrewID is **AES-256 encrypted**; the device decrypts to display, the SD holds only ciphertext.
- The key lives in the firmware + `secret.key` on your laptop — never on the SD or in the cloud.
- Protects against a lost SD card / copied files. Does not, by itself, stop someone
  dumping the ESP32 flash (that would need flash-encryption + secure-boot).

## Documentation
- `TESTING.md` — how to run the automated test suite (`pytest`) and what each
  test protects; `docs/TESTING_PLAN.md` is the strategy behind it.
- `docs/TESTING_GUIDE.md` — step-by-step walkthrough, key → firmware → register →
  tap → download → gradebook, plus host/container setup, upload troubleshooting, and
  recovering an unsynced log.
- `software/SERIAL_BRIDGE.md` — using the board's serial port from inside the dev container.
- `docs/DESIGN_NOTES.md` — why it's built this way: hardware choices, the card-ID
  format quirks, firmware gotchas, case design, security model, gradebook logic.
- `docs/WIRING.md` — pin-by-pin PN532/SD/speaker connections.
- `docs/BOM.md` — parts list.
- `docs/ROADMAP.md` — current status, known issues, optional hardening.
- `case/case_notes.md` — case assembly and every adjustable print parameter.

## Status
Complete and tested end-to-end: case, firmware (with encryption + NTP, no cloud),
registration, decoding, and Canvas gradebook filling. In use in class, with one open
issue: **the reader isn't yet getting WiFi/NTP in the classroom**, so logs come off
unsynced and are dated with `recover_sessions.py`. The firmware has temporary serial
diagnostics for this (see `docs/ROADMAP.md`). Optional future hardening: ESP32
flash-encryption + secure-boot (see `docs/DESIGN_NOTES.md` Section 6).

## License
MIT — see `LICENSE`. Contributions welcome; see `CONTRIBUTING.md`.
