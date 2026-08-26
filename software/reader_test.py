#!/usr/bin/env python3
"""
Reader format test — shows EXACTLY what the USB card reader types when you tap.

Run it, then tap a card. Most of these readers act like a keyboard and press
Enter after the number, so each tap prints a report. If a tap prints nothing,
press Enter once to flush it.

    python3 reader_test.py        (Ctrl-C or type q + Enter to quit)
"""

DEVICE_UID = "0495AA3ACF2290"   # what the attendance reader saw for your card

print("Tap a card on the reader now.")
print("(If nothing prints after a tap, press Enter once. Type 'q' + Enter to quit.)\n")

n = 0
while True:
    try:
        s = input("scan> ")
    except (EOFError, KeyboardInterrupt):
        print("\nbye"); break
    if s.strip().lower() == "q":
        break
    if s == "":
        continue
    n += 1
    up = s.strip().upper()
    print(f"  raw repr : {s!r}")
    print(f"  length   : {len(s)} chars")
    print(f"  char codes: {[hex(ord(c)) for c in s]}")
    print(f"  uppercased: {up}")
    print(f"  == device UID {DEVICE_UID} ?  {'YES ✅' if up == DEVICE_UID else 'no ❌'}")
    print()
print(f"\nCaptured {n} scan(s).")
