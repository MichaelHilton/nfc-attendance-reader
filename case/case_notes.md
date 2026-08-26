# 3D-Printed Desk Case — Attendance Reader (CYD + PN532)

Rebuilt for the **PN532** reader (all-in-one board with a built-in antenna), replacing the old RDM6300 coil + reader corral with a single pocket. Three printed parts: **body**, **lid**, **stand**.

## The design in one look
- **The whole display glass (85 × 55 mm) drops into the front opening**, resting on the 8 mm left/right lips — captured with no pegs.
- **Board held** by the front lip (forward) + four **press-pads on the lid** (backward). The board slides in from the back; the lid ledge is only on the top/bottom walls so the 101.5 mm board clears the sides.
- **Lid retention:** **four screws** — two at the bottom and two at the top (there's now a taller blank strip above the screen to house the top bosses), so the back is held securely all around.
- **PN532 pocket** in the tap zone: a single recessed pocket (~43 × 41 mm) holds the reader flat against the front wall, antenna facing out, behind the "tap here" ring. Two snap clips hold it; a wire notch routes its cable up to CN1.
- **Speaker pocket** to the left of the PN532 — a **round pocket for a Ø20 mm speaker** with a **round sound grille** (center + ring of holes) through the front face, and a **1 cm gap in the ring wall** (top) for the speaker leads.
- **"TAP" label** engraved (debossed) into the front, ringed by a thin groove — both shallow so they print cleanly with the front face on the bed (no big recess to bridge/sag).
- **USB slot** on the **bottom-left edge, 13 mm up from the bottom**, sized **~13 × 8 mm to clear a chunky cable boot** — the board mounts **rotated 180°** so the cable exits low (less wire strain). Set **`tft.setRotation(3)`** in the sketch so the screen isn't upside down.
- Case ~108 × 119 × **25 mm** — deepened to add a **battery bay behind the board** for the LiPo + USB‑C charge/boost module. Rounded outer vertical corners (4 mm radius).
- **Charging:** the 30 × 20 mm charge board sits in a **cradle on the lid** (lower half, below the battery), USB‑C facing a **slot in the bottom wall**. The **power switch** mounts on the **right wall** — actuator through a slot, held by **two screw posts 15 mm apart** that its tiny screws thread into.
- **Battery mounting:** the LiPo tapes into a **shallow corral on the lid** (upper half; a wire gap lets the leads out) — **not** against the board's back, to avoid shorting/puncturing the pouch on the pins. The charge board sits in its own **lid cradle** just below the battery, so both share the lid and their wires stay short.

## Files
- `case_body.stl` — front enclosure: display opening, PN532 pocket + clips, USB slot, tap ring
- `case_lid.stl` — recessed back cover: 4 board press-pads, vents, screw holes
- `case_stand.stl` — desk cradle (~120 × 51 × 71 mm), reclines ~18°
- `case_gen.py` — parametric source (all dimensions at the top)

## Print settings
- PLA or PETG · 0.2 mm layers · 3 walls · 15–20 % infill · **no supports**
- Body & stand base **down**; lid plate **down** (pads point up).
- ~190 g filament total.

## Assembly
1. **PN532:** press it into the front pocket, **antenna side facing the front wall** (behind the tap ring). The two snap clips hold it; a dab of foam tape is a fine backup. Route its 4-wire cable out the pocket notch.
1b. **Speaker:** set it (cone toward the front) into the pocket behind the grille, over on the left; a bit of foam tape holds it. Plug it into the board's SPEAK connector.
2. **Wire to CN1:** one JST 1.25 mm cable — VCC→3V3, GND→GND, SDA→IO21, SCL→IO22. Guide it up through the wire keeper to the board's CN1 socket. Set the PN532 DIP switches to **I2C**.
3. **Display:** slide the CYD in from the back — glass through the front opening, PCB resting on the left/right lips, screen facing out.
4. **Close:** set the lid into the recessed seat and drive **four M3 × 8–10 mm screws** through the lid into the corner bosses (2 top, 2 bottom). The press-pads clamp the board forward.
5. **Stand:** set the unit into the cradle — bottom edge behind the front lip, back on the support.

## Adjustables (top of `case_gen.py`)
- `PN_W` / `PN_H` / `PN_T` — PN532 board size (measure yours; defaults 43 × 41 × 1.6 mm).
- `BL` / `BW` / `comp_h` — display board size and component height.
- `GW` / `GH` / `GDX` — glass size and offset.
- `USB_FROMBOT` / `USB_LEN` / `USB_TALL` — USB slot position/size (now bottom-left).
- `SPK_DIA` / `SPK_T` — round speaker diameter/thickness (default Ø20 × 5 mm); adjust to your speaker.
- `clr` — board-to-wall clearance; `recline` — stand angle; `back_gap` — **battery-bay depth** (raise for a thicker cell).
- `MOD_L` / `MOD_H` / `MOD_T` — charge-board size (now **30 × 20 × 4 mm**); the lid cradle and bottom USB‑C slot both key off these.
- `sw_cy` — switch center height on the right wall; the two screw posts sit ±7.5 mm from it (15 mm apart). `sw_pilots` = pilot-hole size for the screws.
- `usbc` / `psw` boxes — the **USB‑C charge slot** (bottom wall) and **switch actuator slot** (right wall); move to match your parts.
- `BAT_W` / `BAT_H` — battery corral size on the lid (default 55 × 40 mm); **measure your cell and adjust** so it nests snugly.

## Battery wiring (corded USB‑C charging)
- LiPo → charge module BAT (JST‑PH 2.0). Module **USB‑C** faces the bottom cutout.
- Module **5 V out → CYD `VIN` + `GND`** on the P1 connector (4‑pin JST 1.25, use only VIN + GND).
- **Switch** inline on the 5 V line (budget board has no EN pin), poking through the right slot.
- Don't power from USB and VIN at once — run off the battery/VIN path.
- `pad_short` / `pad_short_L` — how much to shorten the lid press-pads (base / far side); increase if they bottom out.
- corner radius: the `4.0` in `rrect_prism(out_w,out_h,out_d,4.0)` — bump up for rounder corners.
