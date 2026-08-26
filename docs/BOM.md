# Bill of Materials

Approximate -- fill in your own prices/links below (component pricing drifts and
varies by source; the placeholders mark where to drop in your own numbers).

| Part | Spec / model | Qty | Source | Approx. cost |
|------|-------------|-----|--------|--------------|
| Display + microcontroller | ESP32-3248S035C ("Cheap Yellow Display" / CYD), 3.5" ST7796, WiFi, microSD slot | 1 | *(fill in)* | *(fill in)* |
| NFC reader | PN532 (13.56 MHz), I2C mode | 1 | *(fill in)* | *(fill in)* |
| Registration reader | USB keyboard-wedge NFC reader, 13.56 MHz (reference build used a BlissKiss unit, Amazon ASIN B0FJ1X7QFJ -- confirm 13.56 MHz support before buying, some listings are ambiguous) | 1 | *(fill in)* | *(fill in)* |
| microSD card | Any size sufficient for a semester's `attendance.csv` (a few MB is plenty) | 1 | *(fill in)* | *(fill in)* |
| Speaker | 8ohm, ~20 mm round (optional -- reader works silently without it) | 1 | *(fill in)* | *(fill in)* |
| NFC-compatible cards/tags | For testing without real ID cards -- any 13.56 MHz NFC card/tag works for bring-up | a few | *(fill in)* | *(fill in)* |
| 3D-printed case | See `case/` -- `case_body.stl`, `case_lid.stl`, `case_stand.stl` (PLA/PETG, ~190 g total) | 1 set | print yourself | filament cost only |
| Case screws | M3 x 8-10 mm (lid), M2.5 self-tapping (~5-6 mm, power switch) | ~6 | *(fill in)* | *(fill in)* |

## Optional -- battery-powered build

| Part | Spec / model | Qty | Source | Approx. cost |
|------|-------------|-----|--------|--------------|
| LiPo battery | Sized to fit the case battery bay (default corral ~55 x 40 mm -- measure your cell) | 1 | *(fill in)* | *(fill in)* |
| USB-C charge/boost module | "V713" or equivalent, ~30 x 20 x 4 mm | 1 | *(fill in)* | *(fill in)* |
| Slide power switch | 19 mm long, mounting holes 15 mm apart, inline, 3 mm holes | 1 | *(fill in)* | *(fill in)* |

## Notes

- Confirm your institution's ID cards are actually 13.56 MHz NFC before building --
  the reference deployment (CMU) uses 13.56 MHz cards; a 125 kHz reader will not
  read them. Check with a phone NFC-scanning app or the card's printed spec.
- `case/case_gen.py` is parametric -- if your PN532 board, speaker, or charge
  module differ in size, adjust the dimensions at the top of that file and
  regenerate the STLs rather than force-fitting the default case.
