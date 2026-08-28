# Testing

How to run the test suite and what each part of it is for. For the *why this
order* strategy and history, see `docs/TESTING_PLAN.md`. For the manual,
device-in-hand walkthrough, see `docs/TESTING_GUIDE.md`.

The suite is Python (`pytest`) and covers everything laptop-side in `software/`,
plus a contract check against the firmware crypto and an optional native compile
of it. No hardware is needed; a full run is ~2 seconds.

---

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

`requirements-dev.txt` pulls in the runtime deps (`cryptography`, `pyserial`)
plus `pytest` and `pytest-cov`. A repo-root `.venv/` is used because the system
Python is externally managed (PEP 668); it is gitignored.

Once the venv exists, just:

```bash
.venv/bin/pytest                 # everything
.venv/bin/pytest -q              # quieter
.venv/bin/pytest --cov           # with a coverage report (gate: 95%, see .coveragerc)
```

Config lives in `pyproject.toml` (`[tool.pytest.ini_options]`): tests are under
`tests/`, and `software/` is put on `sys.path` so tests can
`import attendance_crypto` the same way the scripts import each other.

---

## Running subsets

```bash
.venv/bin/pytest tests/test_gradebook_scoring.py          # one file
.venv/bin/pytest tests/test_gradebook_scoring.py::test_score_tap_tiers
.venv/bin/pytest -k "match or alias"                      # by name substring
.venv/bin/pytest -m "not slow"                            # skip the slow case regen
.venv/bin/pytest -rs                                      # show why anything skipped
```

### Markers

| Marker | Meaning | Runs when |
|---|---|---|
| `slow` | more than a second or two (the full `case_gen.py` regeneration) | always, unless `-m "not slow"` |
| `needs_mbedtls` | needs a C++ compiler **and** pre-4.x mbedTLS headers/libs | auto-skips otherwise |
| `needs_trimesh` | needs the `trimesh` / `manifold3d` / `shapely` / `matplotlib` stack | auto-skips otherwise |
| `hardware` | needs a physical reader / serial port | never in CI; not currently used by any test |

Nothing is silently missing: `-rs` prints a one-line reason for every skip.

---

## Optional suites

Two areas need extra tooling. They **skip cleanly** when it is absent, so a plain
`pytest` is always green.

### Native firmware-crypto check (`test_firmware_crypto_native.py`)

Compiles the real `firmware/attendance_reader_PN532/crypto.hpp` against host
mbedTLS and verifies it produces the shared known-answer vectors. Needs a C++
compiler and the classic (pre-4.x) mbedTLS API.

```bash
# Debian/Ubuntu
sudo apt-get install -y libmbedtls-dev
# macOS (Homebrew's default mbedtls is 4.x and won't work here; use the v3 keg)
brew install mbedtls@3
```

The test discovers mbedTLS via `pkg-config` or a short list of prefixes
(including `/opt/homebrew/opt/mbedtls@3`). It generates `tests/native/_vectors_gen.h`
from `tests/fixtures/crypto_vectors.json` before compiling; that file is
gitignored. If mbedTLS is present but `crypto.hpp` fails to compile, that is a
**hard failure**, not a skip.

### Case geometry (`test_case_gen.py`)

```bash
.venv/bin/pip install -r case/requirements.txt
.venv/bin/pytest tests/test_case_gen.py
```

Regenerating all three STLs takes ~15 s on a cold matplotlib font cache (hence
the `slow` marker on the regeneration test).

---

## What each test file protects

### The core invariant

`software/attendance_crypto.py` (laptop) and the mbedTLS code in the firmware
must produce **byte-identical** tokens and ciphertext, or a roster built on the
laptop won't match cards on the device. Several test files exist only to guard
this.

| File | Goal |
|---|---|
| `test_attendance_crypto.py` | Unit tests for the crypto module: known-answer vectors (the same ones the firmware checks at boot), encrypt/decrypt round-trips over ASCII/Unicode/empty/39-char names, `token()` determinism and key-sensitivity, `load_or_create_key` (mode `0600`, idempotent, rejects bad keys), PKCS7 padding edge cases, and `decrypt_name` failure paths. |
| `test_crypto_contract.py` | The laptop/firmware contract, driven by `tests/fixtures/crypto_vectors.json`: (1) `attendance_crypto.py` reproduces every vector; (2) the firmware source still carries the literal token / ciphertext / plaintext for the vectors marked `firmware_selftest`. Editing crypto on one side without the other fails here. |
| `test_firmware_crypto_native.py` | Strongest guard: compiles the actual `crypto.hpp` against host mbedTLS and checks the same vectors plus `uidToKey`. Gated (`needs_mbedtls`). |

### Gradebook (`software/build_gradebook.py`)

The densest logic — name matching and Present/Late/Absent scoring on top of a
Canvas CSV rewrite. `main()` was split into `parse_args` / `build() -> Result` /
`render_report` / `write_output` so the logic is testable without scraping stdout.

| File | Goal |
|---|---|
| `test_gradebook_helpers.py` | Pure helpers: `norm_tokens` (order/case/punctuation independence), `fmt_points` (integer vs fraction formatting), `col_label` (stripping the trailing `(id)`), and the roster/alias loaders. |
| `test_gradebook_matching.py` | `match_row` against a tiny `CanvasIndex`: alias → SIS Login ID, exact normalized match, ambiguous (two students, same name), subset/superset "approx" match for middle initials, and the no-match case. |
| `test_gradebook_scoring.py` | `score_tap` tier boundaries (inclusive), tapped-before-start, `late_frac` points, earliest-tap-of-the-day wins, and multiple cards for one student keeping the best status. |
| `test_gradebook_columns.py` | Resolving `--column` (exact label vs substring, zero/ambiguous → exit) and reading `Points Possible` (missing / non-numeric → default 1.0 with a warning). |
| `test_gradebook_output.py` | Output integrity: only the target column changes, row count preserved, short rows padded; date filtering (`unsynced-*` counted not scored, wrong-date and malformed timestamps skipped); every report branch; `build()`'s `SystemExit` guards. |
| `test_gradebook_cli.py` | The thin CLI wrapper: `parse_args` defaults, `main(argv)` happy path, the Points-Possible warning print, missing-file exit, default output path. |

### Other laptop scripts

| File | Goal |
|---|---|
| `test_decode.py` | `software/decode_attendance.py`: `find_token_column`, `read_attendance` for both input formats (device `millis,token` and a sheet export with a `token` header) including the `time_col` selection edge, `token_to_name` decrypt/failure handling, and the extracted `decode()` / `main()`. |
| `test_register_core.py` | `software/register_cards.py` roster core (the tkinter GUI is out of scope): `normalize_key` (digit-strip, zero-pad, mod 2³² wrap), `load_roster`/`save_roster` round-trip (sorted, header, 32-char filter), `upsert` (added vs updated, returns previous value, count). |
| `test_sd_download.py` | `software/sd_download.py` parsers split out of the serial loop: `parse_dump` (between `<<<BEGIN>>>`/`<<<END>>>` markers), `parse_count`, and `find_port` matching rules. The serial I/O itself is `# pragma: no cover`. |
| `test_sd_upload.py` | `software/sd_upload.py` framing helpers split out of the serial loop: `checksum` (32-bit wrap), `build_header` (`<length> <checksum>`), `find_marker`, and `parse_result` (`<<<OK>>>`/`<<<ERR>>>` reply). The serial I/O itself is `# pragma: no cover`. |

### End-to-end

| File | Goal |
|---|---|
| `test_pipeline_e2e.py` | Golden test of the whole laptop chain: generate key → build `roster.csv` through the registration core → simulate a class of taps with `helpers.simulate_tap()` (the firmware oracle — it emits the exact `timestamp,token` rows the device logs) → `decode_attendance` → `build_gradebook` against `tests/fixtures/pipeline/Grades.csv`. The decoded report and the filled Canvas CSV are compared byte-for-byte against `tests/fixtures/pipeline/golden/`. Scenario covers present/late/absent, alias and approx matches, an unregistered card, an `unsynced-` row, a wrong-day row, and earliest-tap-wins. Also checks `uid_to_key` against the `DESIGN_NOTES` §2 example. |
| `test_case_gen.py` | `case/case_gen.py`: the committed STLs load and are watertight, and a fresh regeneration produces watertight meshes whose bounding boxes are within 1 mm of recorded baselines. Gated (`needs_trimesh`). |
| `test_smoke.py` | Phase-0 harness check: `software/` is importable, fixtures load. |

### Support files

- `tests/conftest.py` — shared fixtures (`kat_key`, `crypto_vectors`, `key_file`),
  the `--update-golden` option, and `assert_golden()`.
- `tests/helpers.py` — builders for Canvas / roster / attendance CSV fixtures, and
  the firmware oracles `simulate_tap()` and `uid_to_key()`.
- `tests/fixtures/crypto_vectors.json` — the single source of truth for the crypto
  known-answer vectors (shared by the Python and native tests).
- `tests/fixtures/pipeline/` — inputs (`Grades.csv`, `aliases.csv`) and committed
  `golden/` outputs for the end-to-end test.
- `tests/native/crypto_kat.cpp` — the native harness for `crypto.hpp`.

---

## Coverage

`pytest --cov` measures `software/` (see `.coveragerc`). `run_gui`, `__main__`
blocks, and serial I/O are excluded. The gate is **95%**; the suite currently
sits at ~99% (`build_gradebook`, `decode_attendance`, `register_cards`,
`sd_download` at 100%, `attendance_crypto` at 96%).

```bash
.venv/bin/pytest --cov --cov-report=term-missing   # per-line misses
.venv/bin/pytest --cov --cov-report=html && open htmlcov/index.html
```

---

## Updating golden files

`test_pipeline_e2e.py` compares against committed files in
`tests/fixtures/pipeline/golden/`. When you change output on purpose:

```bash
.venv/bin/pytest tests/test_pipeline_e2e.py --update-golden
git diff tests/fixtures/pipeline/golden/     # review every changed line
```

Only run this when the change is intended — the point of the golden files is that
an *unintended* output change fails CI.

---

## CI

`.github/workflows/tests.yml` runs on every push and PR:

- **pytest** — the full suite on Python 3.11–3.14, with `libmbedtls-dev`
  installed so the native crypto test runs. Coverage gate enforced.
- **case-geometry** — `test_case_gen.py` on one Python version with the geometry
  stack installed.
- **arduino-compile** — compiles the ESP32 sketch to catch syntax/API breakage.
  Non-blocking for now (`continue-on-error: true`); the board-package download is
  slow and flaky.

---

## Adding tests

- New tests go in `tests/test_*.py`; functions are `test_*`.
- Reuse `tests/helpers.py` for CSV fixtures and `tests/conftest.py` for the KAT
  key / vectors. Build temp files under `tmp_path`.
- If you touch the crypto on either side, add or update a row in
  `tests/fixtures/crypto_vectors.json` and keep the firmware self-test literals in
  step (`test_crypto_contract.py` will tell you if they drift).
- Keep `software/` coverage at or above the gate; exclude genuinely
  hardware-only code with `# pragma: no cover` and a short reason.
