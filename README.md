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
- **software/** — laptop-side Python (needs `pip install cryptography pyserial`)
  - `attendance_crypto.py` — shared crypto (keys, tokens, name encryption)
  - `register_cards.py` — registration station GUI → builds encrypted `roster.csv`
  - `decode_attendance.py` — turns logged tokens back into names
  - `build_gradebook.py` — fills a Canvas attendance column (Present/Late/Absent) from the log
  - `reader_test.py` — shows exactly what the USB registration reader types
  - `sd_download.py` — pulls `attendance.csv`/`roster.csv` off the device over USB serial
  - `aliases.csv` (copy from `aliases.csv.example`) — `typed_name,sis_login_id` fixups for names that don't match Canvas

## How the pieces fit
1. **Generate the key (once):** `python3 software/attendance_crypto.py` → creates
   `secret.key` (keep private!) and writes `secret_key.h` straight into
   `firmware/attendance_reader_PN532/` — nothing to paste, and it's gitignored.
2. **Flash the device:** copy `wifi_config.h.example` to `wifi_config.h` in that same
   folder and fill in your network, then upload the sketch. The Serial Monitor should
   print `crypto self-test: HMAC OK, AES OK`.
3. **Register students:** `python3 software/register_cards.py` — each student taps and
   types their name → writes `roster.csv` (only `token,encrypted_name`). Copy it to the SD card.
4. **In class:** the device reads cards, shows names, logs `timestamp,token` to the SD
   (WiFi sets the clock over NTP; no cloud).
5. **Grade:** pull the log with `sd_download.py`, then run `build_gradebook.py` with the
   session date/time and the Canvas column to fill — it writes a Canvas-importable CSV
   (Present/Late/Absent, absent = 0). `decode_attendance.py` gives a plain names+times list
   if you just want to read the log.

Example gradebook run:
```
python3 software/build_gradebook.py --canvas Grades.csv --attendance attendance.csv \
    --date 2026-08-25 --start 10:00 --late-after 10 --close 30 --late-frac 0.5 \
    --column "Aug 25 Activity"
```
Names that don't match Canvas are reported; pin them once in `aliases.csv`
(`typed_name,sis_login_id`) and re-run.

## Security model
- Card numbers are **never** written to disk — only `token = HMAC-SHA256(key, id)`.
- Names are **AES-256 encrypted**; the device decrypts to display, the SD holds only ciphertext.
- The key lives in the firmware + `secret.key` on your laptop — never on the SD or in the cloud.
- Protects against a lost SD card / copied files. Does not, by itself, stop someone
  dumping the ESP32 flash (that would need flash-encryption + secure-boot).

## Documentation
- `TESTING.md` — how to run the automated test suite (`pytest`) and what each
  test protects; `docs/TESTING_PLAN.md` is the strategy behind it.
- `docs/TESTING_GUIDE.md` — step-by-step walkthrough, key → firmware → register →
  tap → download → gradebook, plus upload troubleshooting.
- `docs/DESIGN_NOTES.md` — why it's built this way: hardware choices, the card-ID
  format quirks, firmware gotchas, case design, security model, gradebook logic.
- `docs/WIRING.md` — pin-by-pin PN532/SD/speaker connections.
- `docs/BOM.md` — parts list.
- `docs/ROADMAP.md` — current status, known issues, optional hardening.
- `case/case_notes.md` — case assembly and every adjustable print parameter.

## Status
Complete and tested end-to-end: case, firmware (with encryption + NTP, no cloud),
registration, decoding, and Canvas gradebook filling. Optional future hardening: ESP32
flash-encryption + secure-boot (see `docs/DESIGN_NOTES.md` Section 6).

## License
MIT — see `LICENSE`. Contributions welcome; see `CONTRIBUTING.md`.
