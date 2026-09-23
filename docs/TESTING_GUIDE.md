# Attendance Reader — End-to-End Test Guide (from zero)

A step-by-step walkthrough for testing the whole system from a clean slate:
**key → firmware → register cards → tap in class → download log → gradebook.**

Everything laptop-side runs from the `software/` folder unless noted. The reader
plugs into the Mac over USB. Read **Step 0** first if you work in the dev container:
some commands have to run on the Mac itself.

The pipeline:

```
[1] generate key ──► [2] flash firmware ──► [3] register cards ──► roster.csv ─► SD
                                                                                  │
   Canvas CSV ◄── [6] build gradebook ◄── [5] download+decode ◄── [4] tap cards ◄┘
```

---

## Step 0 — Where to run what: dev container vs. host

The dev container can't see the Mac's USB ports (Docker Desktop doesn't forward
USB), so anything that talks to the board directly runs **on the host**:

| Runs on the **host** (Mac) | Runs anywhere (container or host) |
|---|---|
| `firmware/flash.sh` upload (container: `-n` compile only) | `attendance_crypto.py` (key generation) |
| Arduino IDE / `arduino-cli monitor` (Serial Monitor) | `register_cards.py`: in the container, use the browser desktop below |
| `sd_download.py`, `sd_upload.py`, `reader_test.py`, unless you use the serial bridge | `decode_attendance.py`, `build_gradebook.py`, `recover_sessions.py` |
| `software/serial_bridge_host.sh` (the host half of the bridge) | the test suite (`pytest`) |

**Host virtualenv.** The Mac's Homebrew Python is externally managed (PEP 668), so
the host-side scripts run from a virtualenv at `software/path/to/venv` (gitignored).
It only needs the runtime dependencies (`cryptography`, `pyserial`). One-time setup,
**on the host**, from `software/`:

```bash
cd software
python3 -m venv path/to/venv
path/to/venv/bin/pip install -r requirements.txt
```

After that, in each host terminal session:

```bash
cd software
source path/to/venv/bin/activate      # now `python3` has cryptography + pyserial
python3 sd_download.py
```

(or skip `activate` and call `path/to/venv/bin/python3 sd_download.py` directly).

This venv, like the repo-root `.venv/` (the host's test venv, see `TESTING.md`),
holds macOS binaries and **does not work inside the container**. That's expected.
The container doesn't need it: `postCreateCommand` installs `requirements-dev.txt`
into the container's own Python, so there you just run `python3 …`.

**Using the board from inside the container anyway.** Instead of switching to the
host, you can bridge the serial port into the container over TCP. See
`software/SERIAL_BRIDGE.md`. The bridge works for `sd_download.py`, `sd_upload.py`
and `reader_test.py`, but **not** for flashing.

**GUI in the container.** `register_cards.py` needs a display. The container runs
a lightweight desktop served over noVNC: open the forwarded port **6080** in a
browser (password `vscode`), open a terminal there, and run the script. The USB
registration reader "types" into whatever window has focus, so keep the noVNC
browser tab focused while students tap.

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

Either the Arduino IDE (2a) or the `firmware/flash.sh` script (2a-alt). Flash from
the **host** the board is plugged into — USB flashing does not work through
`software/serial_bridge.sh`.

### 2a-alt. Scripted (arduino-cli)

One-time: `./firmware/setup-arduino.sh` (installs arduino-cli, the ESP32 core, and
the libraries; still needs a `User_Setup.h` for the 3.5" ST7796 CYD — see
`docs/DESIGN_NOTES.md`). The devcontainer installs arduino-cli on create, so there
you only need to run `setup-arduino.sh` once for the core + libraries.

```
./firmware/flash.sh            # auto-detect port, compile + upload
./firmware/flash.sh -n         # compile only (no board needed)
./firmware/flash.sh /dev/cu.usbserial-XXXX
```

Then confirm the boot output as in step 6 below. Inside the devcontainer only
`-n` works — the host USB port isn't visible to the container.

### 2a. Normal flow

1. Plug the CYD reader into the Mac with a **data** USB cable, **directly** (no hub/dock).
2. Open `firmware/attendance_reader_PN532/attendance_reader_PN532.ino` in Arduino IDE.
3. **Tools → Board**: the ESP32 board for the CYD (e.g. *ESP32 Dev Module*).
4. **Tools → Port**: select the `/dev/cu.usbserial-…` port.
5. Click **Upload**.
6. Open **Serial Monitor at 115200 baud** and confirm the boot lines:
   ```
   crypto self-test: HMAC OK, AES OK
   Serial commands: dump | roster | upload | count | help
   ```
   The screen should show **Ready** — green if an SD card is inserted, orange if not.
   The top bar shows the clock (`clock not set` until WiFi + NTP sync, then
   `YYYY-MM-DD HH:MM:SS`) on the left and `WiFi` / `no WiFi` on the right.

   The firmware currently also prints **temporary WiFi diagnostics** on the same
   serial port. At boot it lists every 2.4 GHz network it can see and flags whether
   your `WIFI_SSID` is among them. After that it prints the status every 2 s until
   WiFi and NTP are both up:
   ```
   [wifi] target SSID="MyNetwork"  pass length=12
   [wifi]   1) MyNetwork                        RSSI  -48  ch  6  secured   <-- MATCH
   [wifi] status=DISCONNECTED
   [wifi] CONNECTED  ip=172.20.10.3  gw=172.20.10.1  rssi=-47 dBm
   [ntp]  clock set: 2026-09-23 10:02:11
   ```
   `NO_SSID_AVAIL` means the network isn't visible (5 GHz-only, or a phone hotspot
   without *Maximize Compatibility*). `CONNECT_FAILED` usually means a wrong
   password. From the command line: `arduino-cli monitor -p <port> -c baudrate=115200`
   (on the host).

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
2. For each test student: **tap the card**, then **type the AndrewID** (2-8 characters)
   and press **Enter**. The AndrewID is AES-encrypted; only `token,enc` is written —
   the card number is never stored.
   - If the student taps **again** while the AndrewID prompt is up, the reader types
     the card number into the box. An all-digit entry is rejected ("That's a card tap,
     not an AndrewID"), so it can't be saved as an AndrewID. Just type the AndrewID.
   - Tapping an already-registered card and entering a new AndrewID **updates** that
     card (the screen shows the previous value).
3. Register at least **2 cards** so we can see present/absent behavior later.
4. Press **Esc** to quit. This produces:
   - `software/roster.csv`: `token,encrypted_andrewid`, rewritten in full on every save.
   - `software/registration_log.csv`: `timestamp,token`, one line appended per
     **new** card. This is the only record of *when* each card was registered.
     `build_gradebook.py` uses it to credit students who registered in class but
     never tapped the reader (Step 6). Keep it next to `roster.csv`. Both files are
     gitignored.
5. Get `roster.csv` onto the device, either:
   - **over USB** (device plugged in, no SD removal):
     `python3 sd_upload.py roster.csv` (host, or via the serial bridge). The device
     swaps it in and reloads without a reboot. Or:
   - **copy it to the SD card** (root of the card, filename `roster.csv`), re-insert
     the card, and power-cycle the reader.

   The screen should show `N in roster`.

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
The `sd_*` commands run **on the host** in the host venv (Step 0) or through the
serial bridge.

1. Pull the log off the device over USB:
   ```bash
   cd software
   python3 sd_download.py                 # auto-detects port → attendance.csv
   # if auto-detect misses: python3 sd_download.py --port /dev/cu.usbserial-XXXX
   python3 sd_download.py --cmd count      # quick row count
   python3 sd_download.py --cmd roster     # pull roster.csv back for a check
   ```
   To push a **new** roster.csv to the device without pulling the SD card:
   ```bash
   python3 sd_upload.py roster.csv        # sends it over USB; device swaps it in and reloads
   python3 sd_download.py --cmd roster    # read it back to confirm
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
attendance assignment column already created. No real course handy? Copy
`software/Grades.csv.example` to `Grades.csv` and try the command below as-is —
it's a fake 3-student roster shaped exactly like a real Canvas export.

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
present/late/absent counts, plus any **unmatched IDs**, **ambiguous IDs**,
**unregistered cards**, and **unsynced taps**.

AndrewIDs match Canvas by the local-part of `SIS Login ID`. Fix anything that
still doesn't match once in `software/aliases.csv` (start from
`aliases.csv.example`):
```
typed_value,sis_login_id
jdoe,jdoe2@example.edu
```
then re-run. Import `Grades_filled.csv` back into Canvas.

**Students who registered but never tapped.** If `registration_log.csv` (from
Step 3) is in the working directory, a student with **no tap** on `--date` but a
card **registered that day** is scored from the registration time, using the same
present/late/absent windows. This covers registering students in class before the
reader was running. A real tap always takes priority. The report lists these
students (`N student(s) had no tap but registered a card this date…`). Point
elsewhere with `--registration-log PATH`. A missing file is fine (nothing is
credited).

**Canvas export quirks handled.** Some exports have an extra posting-policy row
(`Manual Posting`) between the header and `Points Possible`. That's detected
automatically. Student rows are still recognized by an `@` in `SIS Login ID`.

---

## Step 7 — Recovering a log whose clock never synced

If WiFi/NTP never connected, every row in `attendance.csv` is
`unsynced-<millis-since-boot>,token` and Step 6 scores no one (the report shows
them all as unsynced). `recover_sessions.py` gives those rows real dates:

1. **List the sessions.** Each power-on of the reader is one session (millis reset
   to ~0 at boot). Run it once without `--map`. It prints one line per session:
   ```bash
   python3 recover_sessions.py attendance.csv --out /dev/null
   ```
   ```
   session 5: 64 taps, 63 cards, lines 126-189, 37 min span  (unmapped)
   session 6: 1 taps, 1 cards, lines 190-190, 0 min span  (unmapped)
   session 9: 8 taps, 1 cards, lines 324-331, 2 min span, synced 2026-09-11 11:53:27 .. …
   ```
   A ~class-sized session lasting about a class period is a real class. A handful
   of taps from one card is a test.
   Rows with truncated tokens or garbled timestamps (from a torn SD write) are
   reported on stderr and dropped.
2. **Work out which date each session was.** Use the number of taps, who tapped,
   any nearby synced timestamps, and your class calendar. Power-ons that were just
   testing can simply be left unmapped.
3. **Map and write:**
   ```bash
   python3 recover_sessions.py attendance.csv \
       --map 5=2026-08-28 --map 7=2026-09-08 \
       --out attendance_recovered.csv
   ```
   It prints who was present on each recovered date. Synced rows are kept as-is,
   and unsynced rows in unmapped sessions are dropped.
4. **Grade each recovered date with `--start 00:00`.** A recovered tap's time of
   day is the time since that session's **first tap** (first tap = `00:00:00`).
   That assumes the reader was switched on at about class start:
   ```bash
   python3 build_gradebook.py --canvas Grades.csv --attendance attendance_recovered.csv \
       --date 2026-08-28 --start 00:00 --late-after 10 --close 30 --column "Aug 28 Activity"
   ```
   If the reader was switched on well before class, late/absent cutoffs will be
   off by that much. Sanity-check the printed lists before importing.

`attendance_recovered.csv` contains tokens only, but it's still student attendance
data. It's gitignored, like the other logs.

---

## Quick command reference

**Host** = run on the Mac in the host venv (`source path/to/venv/bin/activate`,
Step 0), or through the serial bridge.

| Task | Command (run from `software/`) | Where |
|------|--------------------------------|-------|
| Generate/inspect key | `python3 attendance_crypto.py` | anywhere |
| Flash firmware | `../firmware/flash.sh` (`-n` = compile only) | host (compile: anywhere) |
| Register cards | `python3 register_cards.py` | anywhere (container: noVNC, port 6080) |
| See what the USB reader types | `python3 reader_test.py` | host |
| List serial ports | `ls /dev/cu.*` | host |
| Push roster to device | `python3 sd_upload.py roster.csv` | host |
| Download attendance log | `python3 sd_download.py` | host |
| Count logged rows | `python3 sd_download.py --cmd count` | host |
| Decode log → names | `python3 decode_attendance.py` | anywhere |
| Build gradebook | `python3 build_gradebook.py --canvas … --date … --start … --column …` | anywhere |
| Date an unsynced log | `python3 recover_sessions.py attendance.csv --map N=YYYY-MM-DD` | anywhere |

Device serial commands (in Serial Monitor): `dump` · `roster` · `count` · `help`.

---

## Known limitation: classroom WiFi for NTP

**Status: not yet working in class.** Enterprise WiFi (eduroam and similar campus
networks) needs more than `WiFi.begin(ssid, pass)`, so the clock may not sync on
those networks. Options:

- A **phone hotspot** for the first minute (just to set the clock). On an iPhone,
  turn on *Personal Hotspot → Maximize Compatibility*: the ESP32 only has a
  2.4 GHz radio and won't see a 5 GHz-only hotspot. Put the hotspot's exact name
  in `WIFI_SSID`.
- A network that accepts a plain SSID + password.
- Accept `unsynced` rows and date them afterwards with `recover_sessions.py`
  (Step 7).

The serial diagnostics described in Step 2a show exactly which case you're in.
