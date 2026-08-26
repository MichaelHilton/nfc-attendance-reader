# Wiring Reference

Pin assignments as used in `firmware/attendance_reader_PN532/attendance_reader_PN532.ino`.
If you deviate from the reference hardware, update the `#define`s near the top of the
sketch to match.

## PN532 NFC reader (I2C, via the CYD's CN1 header)

Set the PN532's DIP switches to **I2C** mode before wiring.

| PN532 pin | CYD pin |
|-----------|---------|
| VCC       | 3V3     |
| GND       | GND     |
| SDA       | IO21    |
| SCL       | IO22    |

IRQ is unused (the firmware polls; `PN532_IRQ` is set to `255`).

## microSD card (SPI, built into the CYD)

| Signal | GPIO |
|--------|------|
| SCK    | 18   |
| MISO   | 19   |
| MOSI   | 23   |
| CS     | 5    |

## Speaker

An 8ohm speaker (the reference build uses a 20 mm round speaker) connects to the
board's **SPEAK** connector, driven from **GPIO26**. Optional -- the reader works
silently without one.

## Power (battery build only)

See `docs/DESIGN_NOTES.md` Section 5 for the full reasoning. In short:

- Charge module **5V output -> CYD `VIN` + `GND`** (P1 header), routed through the
  power switch.
- Charge module **battery pads -> LiPo** (JST-PH 2.0).
- Charge via the **bottom USB-C** (charge module) only -- the CYD's own micro-USB
  is the programming port and does not charge the battery. Never power both at once.

## Board reference

- **ESP32-3248S035C** ("Cheap Yellow Display" / CYD, 3.5" ST7796 screen) --
  ESP32-WROOM-32 (4 MB flash, no PSRAM), CH340 USB-serial.
- Registration station uses a separate **USB keyboard-wedge NFC reader** plugged
  into the instructor's laptop -- no GPIO wiring involved, it just types.
