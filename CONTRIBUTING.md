# Contributing

Issues and pull requests are welcome -- this started as a single classroom's
tool, and adapting it to other courses, LMSs, and hardware variants is exactly
the kind of contribution that's useful.

## Good first contributions

- Adapting `build_gradebook.py` for LMSs other than Canvas.
- Reports of what broke on hardware other than the reference ESP32-3248S035C /
  PN532 combination.
- Documentation fixes -- if a step in `docs/TESTING_GUIDE.md` didn't work for
  you, that's a bug in the docs.
- `case/case_gen.py` variants for different PN532 boards, speakers, or
  enclosures.

## Before opening a PR

- Never commit real student data, a real `secret.key`/`secret_key.h`, or real
  WiFi credentials -- check `.gitignore` covers anything new you add that could
  contain them. That includes every derived file: registration logs, recovered
  or decoded attendance, per-student reports, and Canvas exports (which Canvas
  names like `2026-09-11T0947_Grades-<course>.csv`). Test fixtures use made-up
  names only. Run `git status --ignored` before committing if unsure.
- If you change the crypto (`software/attendance_crypto.py` or the firmware's
  mbedTLS calls in `crypto.hpp`), keep both sides byte-for-byte compatible --
  update `tests/fixtures/crypto_vectors.json` and the firmware self-test
  literals together; `tests/test_crypto_contract.py` fails if they drift.
- Run the test suite:

  ```bash
  python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
  .venv/bin/pytest
  ```

  Inside the dev container the deps are preinstalled, so just run
  `python3 -m pytest` (a `.venv` made on the host won't run there). CI runs the
  same on Python 3.11–3.14. `TESTING.md` explains how to run subsets
  and what each test file protects; `docs/TESTING_PLAN.md` is the strategy behind
  it.
- For changes without test coverage yet, also run the relevant Python script
  against the `.example` fixtures to confirm it still works from a clean clone.

## Reporting security issues

This project's threat model is documented in `docs/DESIGN_NOTES.md` (Section 6)
-- it protects against a lost SD card, not a determined attacker with physical
access to the device's flash. If you find a way to recover student data beyond
what that section already describes as out of scope, please open an issue.
