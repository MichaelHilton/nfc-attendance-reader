# Design Notes, Decisions & Lessons Learned

A running record of *why* this project is built the way it is — the dead ends, the
gotchas, and the decisions behind them. The `README.md` covers how to use everything;
this doc is the reasoning and the hard-won lessons. Newest context is folded in
throughout.

---

## 1. Hardware choices

**Controller — ESP32-3248S035C ("Cheap Yellow Display" / CYD, 3.5").**
Chosen because it bundles what the project needs on one cheap board: an ESP32-WROOM-32,
a 3.5" ST7796 touchscreen, WiFi, and a microSD slot, with a built-in rechargeable-battery
path via VIN. Key facts that bit us or mattered later:
- It's an **ESP32-WROOM-32**, *not* an S3 — 4 MB flash, **no PSRAM**, and a **CH340**
  USB-serial chip. The CH340 is why upload speed matters (below).
- Real board dimensions (from the datasheet, measured): **101.5 × 54.9 × 1.6 mm**, with
  ~5 mm of component height on the back and an **85 × 55 mm** glass area. Our first case
  used a wrong width (85.5 mm) and didn't fit — always use the datasheet numbers.
- Free GPIO is scarce; the speaker amp is on **GPIO26**, and the reader uses the **CN1**
  I2C header (**SDA=IO21, SCL=IO22**).

**Reader — PN532 (13.56 MHz NFC), not 125 kHz.**
The whole reason we're on 13.56 MHz: the CMU ID cards are **13.56 MHz**. This was
confirmed with NFC Tools on a phone (same serial twice) and by the card's 7-byte UID.
A 125 kHz reader cannot read these cards. We do **not** use the fobs. The PN532 talks
**I2C** (set its DIP switches to I2C).

**Registration reader — USB keyboard-wedge (BlissKiss, Amazon B0FJ1X7QFJ).**
Despite an online listing describing it as 125 kHz, the actual unit **does read our
13.56 MHz cards**. It acts like a keyboard: on a tap it "types" a number and presses Enter.

---

## 2. The card-ID format saga (important)

The device (PN532) reads the full **7-byte UID**. Example card: `04 95 AA 3A CF 22 90`.

The USB registration reader types **`0984257796`** for that same card. Decoding that:
`0984257796` = `0x3AAA9504` = the **first 4 UID bytes, little-endian** (`04 95 AA 3A` →
`3A AA 95 04`), as a zero-padded 10-digit decimal.

So the two devices see the same card differently. You **cannot** rebuild the full 7-byte
hex from 4 bytes, so we made the **firmware match the reader**: `uidToKey()` takes the
first 4 UID bytes, little-endian, and formats `%010lu`. Both sides now produce the
identical id string, so registration and reading line up. Using 4 bytes is plenty unique
for a class.

**Lesson:** whenever a second reader is involved, test what it actually emits
(`software/reader_test.py`) before assuming a format. The fix was to standardize on the
constrained device's output.

---

## 3. Firmware architecture & gotchas

- **Upload reliability (CH340):** set **Upload Speed = 115200** in the Arduino IDE.
  921600 fails intermittently on the CH340 ("failed to connect / verify flash").
- **Use the Upload arrow, not Debug.** Hitting Debug triggers OpenOCD and an FTDI error.
- **Pick the right port:** `/dev/cu.usbserial-…`, *not* `/dev/cu.debug-console`. Install
  the **CH340 driver** on macOS if the port doesn't appear.
- **PN532 bring-up is flaky right after a reset.** The fix that made it reliable: a
  **retry loop** (call `getFirmwareVersion()` up to ~12× with short delays) before giving
  up, and use `readPassiveTargetID(…, 300)` with a timeout. Removing
  `setPassiveActivationRetries` fixed reads that stopped after the first card.
- **Screen orientation:** the board is mounted **rotated 180°** so the USB cable exits
  low (less strain), so the sketch sets **`tft.setRotation(3)`** to flip the display back.
- **Non-blocking design:** the UI redraws only the center text band (`drawStatus`) and a
  millis timer clears the result (no `delay`), so scanning never stalls.
- **Time & no cloud:** the Google Apps Script upload was removed. WiFi now exists **only to
  set the clock via NTP** (`configTzTime`, TZ = US Eastern). Each tap logs a real local
  `timestamp,token`; before the clock syncs, rows are logged `unsynced-<millis>` and the
  gradebook script skips/flags them.
- **Two different CSV files, don't confuse them:** `roster.csv` (the id/token → name
  lookup you build) vs `attendance.csv` (the log the device writes). Editing the wrong
  one is an easy mistake — names come from **roster.csv**.
- **Diagnostics exist for a reason:** `firmware/diagnostics/i2c_scan` (PN532 should appear
  at `0x24`), `pn532_test`, and `speaker_test` isolate wiring/library problems fast.
- **Library note:** the reader uses **Adafruit PN532 + Adafruit BusIO**. An earlier
  RDM6300 approach was abandoned (wrong frequency; its library wasn't in Library Manager).

---

## 4. Case design (parametric, `case/case_gen.py`)

The case is generated in Python (trimesh + manifold3d + shapely), not OpenSCAD (not
available in our tooling). Every dimension is a variable at the top of `case_gen.py`;
re-run it to regenerate the three STLs. `case_notes.md` lists all adjustables.

Hard-won lessons:
- **Print orientation drives everything.** The body prints **front-face-down** for a crisp
  bezel. That means *every feature on the front face is a recess that must bridge*. A big
  recess sags.
  - The original **"TAP" marker was a 34 mm filled recess** with raised letters floating
    in it → the floor bridged 34 mm and **sagged, melting into the letters**. Fixed by
    making the ring a **thin groove** and the **"TAP" text engraved** (debossed) — small
    bridges print clean. Paint-fill the engraving for contrast.
- **Mounting:** the glass **drops into the front opening** and rests on side lips; the PCB
  is held forward by that lip and backward by **four press-pads on the lid**. The lid is
  held by **four M3 screws** (2 top, 2 bottom) — an earlier snap lip was too fragile, so we
  raised the top blank strip (`top_bez`) to house the top screw bosses.
- **USB slot** went through several tries: wrong side, wrong size, then correct after
  accounting for the 180° board rotation → **bottom-left, sized ~13 × 8 mm** to clear a
  chunky cable boot.
- **PN532 pocket** sits in the tap zone behind the "TAP" ring, antenna facing out, held by
  snap clips + a wire notch. **Speaker** is a round pocket + round grille on the left with
  a wire gap in the ring.
- **Battery bay:** the back was deepened (`back_gap`) into a bay. The **LiPo tapes into a
  corral on the lid**, *not* against the board's back (avoids shorting/puncturing the pouch
  on the pins).

**Charge-module cradle — the fiddly part.** The V713 charge board is **30 × 20 × 4 mm**.
The tap-zone front is full (PN532 fills it; only ~28 mm free to its right — too narrow for
a 30 mm board), so the cradle went **on the lid** instead, in the lower half. It must stand
the board **upright (20 wide × 30 tall)** so the **USB-C short edge lines up with the
bottom-wall hole**. A **peek slot** in the lid shows the charge LEDs — they're in the
board's **top-right corner (1 mm from the right edge, 4–9 mm from the top)**, so mount the
board **LED-side toward the lid**.

**Power switch mounting.** The slide switch is **19 mm long, mounting holes 15 mm apart,
inline, 3 mm holes** → use **M2.5 self-tapping screws (~5–6 mm)** into the **1.9 mm printed
pilots** on two posts. The switch first **collided with a lid press-pad**; rather than move
the pad, we **centered the switch on the right edge between the two right-side pads**.

**General:** always dry-fit and check clearances against the *other* part (lid features vs
body features), since collisions only appear when assembled. Flat gray renders don't show
shallow relief — preview STLs in a slicer with lighting.

---

## 5. Power & charging

- Corded **USB-C charging** via the V713 module. Its pads: **"5V + / −" = OUTPUT**
  (→ CYD **VIN + GND** on the P1 header, through the switch); plain **"+ / −" = BATTERY**
  (→ LiPo). Verify with a multimeter before connecting the CYD (~5 V on the 5V pads,
  ~3.7–4.2 V on the battery pads).
- The **switch** is inline on the 5 V output (the budget module has no enable pin).
- **Charge from the bottom USB-C only** — that's the module. The CYD's own micro-USB (left
  edge) is the *programming* port and does not charge the battery.
- The module is a power-bank-style IC (has a boost inductor), so it generally charges while
  running; if it ever misbehaves plugged in, switch off and charge. **Never** feed the
  CYD's USB and VIN at the same time.
- Charge-status LEDs are inside — hence the lid peek slot (§4).

**TODO — on-screen battery indicator (not yet possible with this wiring).** The V713
module boosts the LiPo to a regulated ~5 V into `VIN`, so the ESP32 sees the same
voltage whether the cell is full or nearly flat — there is nothing to measure at
`VIN`, and the cheap module exposes no charge-status line. Adding a battery gauge to
the top status bar (`drawTopBar()` in the sketch) needs a hardware change, either:
  - a wire from the raw LiPo **+** through a 2×100 kΩ divider into a free **ADC1** GPIO
    (ADC2 is dead while WiFi is on; confirm a genuinely free ADC1 pin against the
    ESP32-3248S035C schematic — GPIO35 on the CN1/P3 header, input-only, is the usual
    candidate), then map ~3.3–4.2 V to a rough percentage (nonlinear, ±10–20%); or
  - a **MAX17048** I²C fuel gauge on the existing PN532 bus (IO21/IO22) for true
    state-of-charge, ~$5.
  Until one of those is added, the firmware deliberately has no battery UI.

---

## 6. Security design (keep card numbers out of plain text)

**The core insight:** "just encrypt the IDs" fails for two reasons at once — the device
must still *match* a tapped card (needs a deterministic transform), and card IDs are
low-entropy (~4 bytes), so any non-secret transform is brute-forceable in minutes. The
answer is a **secret key**:

- **`token = HMAC-SHA256(kmac, id)[:16]`** (32 hex chars). Deterministic so the device can
  match; one-way and not brute-forceable without the key. The **card number is never
  stored** — only its token.
- **Names = AES-256-CBC(kenc, name)** with a random IV, stored as `hex(iv+ciphertext)`.
  The device decrypts to show the name; the SD holds only ciphertext.
- **Subkeys:** `kmac = SHA256("MAC|"+K)`, `kenc = SHA256("ENC|"+K)` from one 32-byte master
  key `K`. `K` lives in the firmware (`SECRET_KEY[32]`) and in `secret.key` on the laptop —
  **never on the SD card or in the cloud.**
- **Cross-platform proof:** Python (`cryptography`/`hmac`) must match the ESP32's mbedTLS
  byte-for-byte. A **boot self-test** on the device uses a fixed vector (key `00..1f`,
  id `0984257796` → token `f989b34da0e80527fc371aabb3ac7402`, and a known encrypted
  "Michael Hilton") and prints `HMAC OK / AES OK`.
- **Files:** `roster.csv` = `token,encrypted_name`; `attendance.csv` = `timestamp,token`.
  The laptop decoder (`decode_attendance.py`) turns tokens back into names.

**Threat model (chosen):** protect against a **lost SD card / copied files** — both become
gibberish without the key. It does **not** stop someone who dumps the ESP32 flash to
extract the key; closing that needs **flash-encryption + secure-boot** (a separate,
larger effort we deferred).

**Decisions made:** device shows the **full (encrypted) name**; the cloud/attendance log
is **tokens only**; **name length ≤ 39 chars** (device buffer).

---

## 7. Gradebook / Canvas integration (implemented)

Goal: an instructor script that fills a **Canvas gradebook** (see the attached export
format) from the attendance data. Canvas CSV structure: `Student, ID, SIS User ID,
SIS Login ID, Root Account, Section`, then assignment columns named `Name (id)`, a
**`Points Possible`** row, and read-only score columns. ~92 students. Attendance is one of
the `1.00`-point activity columns.

Decisions:
- **Cut the Google Apps Script / cloud entirely.** The device just logs to SD.
- **Add NTP** to the firmware (WiFi stays only to set the clock) so each tap is timestamped
  → the script can group by day and compute lateness.
- **Matching:** students **type their AndrewID** (2-8 chars) at registration; the script
  matches it → Canvas **`SIS Login ID`** by local-part (exact, case-insensitive). Older
  rosters that stored a typed name still fall back to name normalization (case, punctuation,
  name order). An **`aliases.csv`** pins oddballs once (`typed_value → SIS Login ID`), and
  an **unmatched report** each run (nothing is silently dropped). We chose *not* to add
  roster autocomplete.
- **Scoring: Present / Late / Absent tiers.** On-time within a window → full points; within
  a later window → partial; otherwise **absent = explicit 0**. Windows/points are per-run
  parameters.
- Output: a **Canvas-importable CSV** (identity columns preserved, one attendance column
  filled) + a summary.

**Implemented in `software/build_gradebook.py`** and tested against the real Canvas export
with a synthetic roster/log. Behavior confirmed: exact and approximate ("Last, First" ↔
"First M Last") name matching, `aliases.csv` overrides, earliest-tap-per-student, on-time
vs late vs after-close scoring, absent = 0, and correct reporting of unmatched names,
unregistered cards, unsynced rows, and wrong-date taps — with every output row keeping the
exact Canvas column count so the file re-imports cleanly.

Matching order per tapped name: (1) `aliases.csv` → SIS Login ID, (2) exact normalized
name, (3) unique subset match (handles middle initials), else reported as unmatched or
ambiguous. Taps after `--close` are scored absent (0). Run it per session with `--date`,
`--start`, `--column`, and the late-window flags.

---

## 8. Quick "if I forget" checklist
- Regenerate `secret.key` (writes `secret_key.h` into the firmware folder automatically) → re-flash → confirm `HMAC OK / AES OK`.
- roster.csv holds **tokens + ciphertext** only; never plain ids/names.
- Print body/lid/stand **face/plate down, no supports**; check "TAP" and the peek slot in
  the slicer.
- Charge via the **bottom USB-C**; program via the **CYD micro-USB**; never both powered at once.
- If names don't show on a tap: it's a **roster.csv** problem (format/key mismatch), and
  check the boot self-test printed OK.
