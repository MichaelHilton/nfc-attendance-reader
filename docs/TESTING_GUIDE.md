# Attendance Reader — End-to-End Test Guide (from zero)

A step-by-step walkthrough for testing the whole system from a clean slate:
**key → firmware → register cards → tap in class → download log → gradebook.**

Everything laptop-side runs from the `software/` folder unless noted. The reader
plugs into the Mac over USB.

The pipeline:

```
[1] generate key ──► [2] flash firmware ──► [3] register cards ──► roster.csv ─► SD
                                                                                  │
   Canvas CSV ◄── [6] build gradebook ◄── [5] download+decode ◄── [4] tap cards ◄┘
```

---

## Step 1 — Generate the key

Run once, from `software/`:

```bash
cd software
python3 attendance_crypto.py
```

This creates:
- `secret.key` — the 32-byte master key (**keep private**, never on SD or in git).
- `secret_key.h` — written directly into `firmware/attendance_reader_PN532/secret_key.h`.
  Nothing to paste — the sketch `#include`s it automatically when the file is present,
  and falls back to a placeholder key (compiles, but won't match a real roster) when
  it isn't.

It's **idempotent**: if `secret.key` already exists it's reused, not overwritten.
The run prints a roundtrip self-test (`roundtrip = <your test name>`) so you know the
crypto works.

Both `secret.key` and `secret_key.h` are gitignored — never commit either one, and
never copy them onto the SD card.

---

## Step 2 — Flash the firmware

### 2a. Normal flow

1. Plug the CYD reader into the Mac with a **data** USB cable, **directly** (no hub/dock).
2. Open `firmware/attendance_reader_PN532/attendance_reader_PN532.ino` in Arduino IDE.
3. **Tools → Board**: the ESP32 board for the CYD (e.g. *ESP32 Dev Module*).
4. **Tools → Port**: select the `/dev/cu.usbserial-…` port.
5. Click **Upload**.
6. Open **Serial Monitor at 115200 baud** and confirm the boot lines:
   ```
   crypto self-test: HMAC OK, AES OK
   Serial commands: dump | roster | count | help
   ```
   The screen should show **Ready** — green if an SD card is inserted, orange if not.

> The self-test uses a fixed test vector, so `HMAC OK, AES OK` proves the crypto
> engine works **regardless of which key is loaded**. The real-key match is proven
> later when a registered card shows the correct name (Step 4).

### 2b. If upload fails with `termios.error: (22, 'Invalid argument')`

This is a **serial-link / upload-speed problem**, not a code problem — the sketch
compiles (≈79% flash). The macOS CH340/CH9102 driver rejected the high upload baud,
and the port often drops off the USB bus afterward. Fix in this order:

1. **Reconnect cleanly.** Unplug the device, wait ~5 s, plug it back in — directly
   to the Mac, known-good **data** cable. Confirm the port reappears:
   ```bash
   ls /dev/cu.*
   ```
   You should see a `cu.usbserial-…` entry. If nothing appears, it's the cable
   or the CH34x driver (see 2c).
2. **Lower the upload speed** — this is the actual fix for the termios error:
   **Tools → Upload Speed → 115200** (down from 921600).
3. **Re-select the port** — **Tools → Port** — the name can change on replug, and
   a stale selection points at a port that no longer exists.
4. **Retry Upload.**
5. **If it still won't connect:** hold the **BOOT** button while the IDE prints
   `Connecting……`, release once it starts writing. Some CYD units need the manual
   boot handshake.

### 2c. If the port never appears (`ls /dev/cu.*` shows nothing)

- Try a different USB cable (many are charge-only) and a different Mac port.
- Confirm the CH34x/CH9102 driver is working. On recent macOS the driver is
  built in; if the device shows in *System Information → USB* but no `cu.usbserial`
  appears, install the WCH CH34x macOS driver and reboot.
- Test the raw port once it's back:
  ```bash
  python3 - <<'PY'
  import serial, glob
  ports = glob.glob("/dev/cu.usbserial*")
  print("ports:", ports)
  if ports:
      s = serial.Serial(ports[0], 115200, timeout=1); s.close(); print("opened OK")
  PY
  ```

---

## Step 3 — Register test cards

The registration reader is the **USB keyboard-wedge** NFC reader (it types the card
number + Enter) — *not* the CYD device.

1. From `software/`:
   ```bash
   cd software
   python3 register_cards.py
   ```
   A full-screen black window opens (green = ready, cyan = saved).
2. For each test student: **tap the card**, then **type the name** and press **Enter**.
   The name is AES-encrypted; only `token,enc` is written — the card number is
   never stored.
3. Register at least **2 cards** so we can see present/absent behavior later.
4. Press **Esc** to quit. This produces `software/roster.csv`.
5. **Copy `roster.csv` onto the device's SD card** (root of the card, filename
   `roster.csv`). Re-insert the SD card into the reader and power-cycle it — the
   screen should show `N in roster`.

> Optional sanity check of what the USB reader actually types:
> `python3 reader_test.py`, then tap a card.

---

## Step 4 — Tap cards "in class"

1. Power the reader with the roster SD card inserted (screen shows **Ready**,
   green, and `N in roster`).
2. Tap each registered card:
   - Known card → **name shown**, high ding, logged as `timestamp,token`.
   - Unknown card → **"Unknown / not registered"**, low buzz (still logged).
3. Confirm the on-screen name matches who you registered — **this is the real-key
   end-to-end proof** (roster built with `secret.key` == key flashed into firmware).
4. Timestamps come from WiFi/NTP. Before the clock syncs, rows are written
   `unsynced-<millis>` and are skipped by the gradebook. A simple home network
   (plain SSID + password) sets the clock fine; **many campus enterprise WiFi
   networks (eduroam and similar) won't work with `WiFi.begin(ssid, pass)`** —
   sort out classroom time-sync separately (see the cleanup note at the end).

---

## Step 5 — Download + decode the log

Close the Arduino **Serial Monitor first** (only one program can hold the port).

1. Pull the log off the device over USB:
   ```bash
   cd software
   python3 sd_download.py                 # auto-detects port → attendance.csv
   # if auto-detect misses: python3 sd_download.py --port /dev/cu.usbserial-XXXX
   python3 sd_download.py --cmd count      # quick row count
   python3 sd_download.py --cmd roster     # pull roster.csv back for a check
   ```
2. Decode tokens → names (laptop-only, uses `secret.key`):
   ```bash
   python3 decode_attendance.py            # attendance.csv + roster.csv here
   ```
   Output `attendance_decoded.csv` has `raw_time,name`. Every registered tap
   should show its name; unknown tokens show `UNKNOWN xxxxxxxx`.

---

## Step 6 — Build the Canvas gradebook

You need a **Canvas gradebook export CSV** (Canvas → Grades → Export) with the
attendance assignment column already created.

```bash
cd software
python3 build_gradebook.py \
    --canvas Grades.csv \
    --attendance attendance.csv \
    --date 2026-08-25 --start 10:00 \
    --late-after 10 --close 30 --late-frac 0.5 \
    --column "Aug 25 Activity"
```

Scoring (per the earliest tap per student that day):
- tap ≤ `--late-after` min after start → **Present** (full points)
- ≤ `--close` min → **Late** (`--late-frac` × points)
- after `--close`, or never tapped → **Absent = 0**

It writes `Grades_filled.csv` (**only the one column changes**) and prints a report:
present/late/absent counts, plus any **unmatched names**, **ambiguous names**,
**unregistered cards**, and **unsynced taps**.

Fix name mismatches once in `software/aliases.csv` (start from
`aliases.csv.example`):
```
typed_name,sis_login_id
Mike Smith,msmith2@example.edu
```
then re-run. Import `Grades_filled.csv` back into Canvas.

---

## Quick command reference

| Task | Command (run from `software/`) |
|------|--------------------------------|
| Generate/inspect key | `python3 attendance_crypto.py` |
| Register cards | `python3 register_cards.py` |
| See what the USB reader types | `python3 reader_test.py` |
| List serial ports | `ls /dev/cu.*` |
| Download attendance log | `python3 sd_download.py` |
| Count logged rows | `python3 sd_download.py --cmd count` |
| Decode log → names | `python3 decode_attendance.py` |
| Build gradebook | `python3 build_gradebook.py --canvas … --date … --start … --column …` |

Device serial commands (in Serial Monitor): `dump` · `roster` · `count` · `help`.

---

## Known limitation: classroom WiFi for NTP

Enterprise WiFi (eduroam and similar campus networks) needs more than
`WiFi.begin(ssid, pass)`, so the clock may not sync on those networks. Options:
a phone hotspot for the first minute (just to set the clock), a network that
accepts a simple SSID, or accept `unsynced` rows and set the date manually.
