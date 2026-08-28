# Testing Plan

How we get this project under automated test, and why in this order. Companion to
`docs/TESTING_GUIDE.md` (which is a manual, hardware-in-the-loop walkthrough) — this
doc is the *automated* strategy: what runs in CI on every push, with no device
plugged in.

The guiding constraint: **the laptop Python and the ESP32 firmware must produce
byte-identical tokens and ciphertext** (`CONTRIBUTING.md`, `DESIGN_NOTES.md` §6).
Most of the test effort exists to protect that and the gradebook logic on top of it.

---

## 0. Status — Phases 0–6 built

All phases below are implemented. `pytest` from the repo root runs green
(~190 tests, <2 s) with **99% line coverage** of `software/` and a 95% gate in
`.coveragerc`. Per-module: `build_gradebook`, `decode_attendance`,
`register_cards`, `sd_download` at 100%; `attendance_crypto` at 96% (the
`os.chmod` fallback). CI (`.github/workflows/tests.yml`) runs the suite on Python
3.11–3.14 plus a `case-geometry` job and a non-blocking `arduino-compile` job.

Notes on what shipped vs. the plan below:

- Deps live in `software/requirements.txt`, `requirements-dev.txt`, and
  `case/requirements.txt`; local dev uses a repo-root `.venv/` (PEP 668).
- `decode_attendance`'s extracted core is `decode()` (the plan said `run()`).
- The native firmware-crypto test (`test_firmware_crypto_native.py`) compiles the
  real `firmware/attendance_reader_PN532/crypto.hpp` against host mbedTLS. It
  canary-probes for the classic pre-4.x mbedTLS API and skips on mbedTLS ≥ 4
  (Homebrew's default) as well as when no compiler/mbedTLS is present; CI installs
  `libmbedtls-dev` so it runs there.
- `test_case_gen.py` also checks the committed STLs load and are watertight, not
  just a fresh regeneration.

---

## 1. Original starting point

There were **no automated tests**, no `pytest` config, and no CI. `cryptography`,
`pytest`, and `pyserial` were not installed. The `.example` fixtures
(`Grades.csv.example`, `aliases.csv.example`, `wifi_config.h.example`) were the
only thing resembling test data, exercised only by hand.

---

## 2. What we're testing, and how testable it is

| Component | Nature | Testability | Priority |
|---|---|---|---|
| `software/attendance_crypto.py` | Pure functions (HMAC token, AES name enc/dec, key mgmt) | Trivial — pure in/out | **Critical** |
| `software/build_gradebook.py` | Name matching + Present/Late/Absent scoring + Canvas CSV rewrite | Helpers pure; `main()` is a ~160-line monolith | **Highest** |
| `software/decode_attendance.py` | Token log → names report; two input formats | Mostly pure, thin `main()` | High |
| `software/register_cards.py` | Roster core (`normalize_key`, `load/save/upsert`) + tkinter GUI | Core is already marked "testable"; GUI is not | High (core only) |
| `software/sd_download.py` | Serial download; `<<<BEGIN>>>`/`<<<END>>>` marker parsing | Parsing tangled with `serial` I/O | Medium |
| `software/reader_test.py` | Interactive diagnostic REPL | Not worth testing | Skip |
| `firmware/attendance_reader_PN532/…ino` | Arduino/ESP32 C++; mbedTLS crypto + UI + SD + NFC | No host build today | Medium (protect crypto only) |
| `case/case_gen.py` | trimesh / manifold3d / shapely / matplotlib geometry | Heavy deps; slow | Low (smoke only) |

---

## 3. Test taxonomy

1. **Unit** — crypto known-answer vectors and properties; name normalization; the
   matching algorithm; the scoring tiers; CSV/format parsers.
2. **Contract** — the Python crypto reproduces the exact vectors hard-coded in the
   firmware's `cryptoSelfTest()`, so drift on either side fails CI.
3. **Golden / end-to-end** — the whole laptop pipeline (key → roster → simulated
   taps → decode → gradebook) against committed fixtures with committed expected
   output.
4. **CLI** — argument parsing, exit codes, and error messages (missing files, bad
   `--date`, ambiguous `--column`).
5. **Gated / optional** — native firmware crypto binary, `arduino-cli` compile,
   `case_gen.py` smoke + dimensional regression. Skipped automatically when their
   toolchain isn't present.

---

## 4. Infrastructure

- `software/requirements.txt` — `cryptography`, `pyserial` (runtime deps, currently
  only named in docstrings).
- `requirements-dev.txt` — `pytest`, `pytest-cov`.
- `pyproject.toml` → `[tool.pytest.ini_options]`:
  - `pythonpath = ["software"]` so `import attendance_crypto as ac` resolves without
    packaging the scripts.
  - `testpaths = ["tests"]`.
  - markers: `hardware`, `slow`, `needs_trimesh`, `needs_mbedtls`.
- `tests/` at the repo root; `tests/fixtures/` holds:
  - `crypto_vectors.json` — the single source of truth for KAT vectors (shared by
    the Python tests and the firmware contract test).
  - `Grades.csv`, `roster.csv`, `attendance.csv` — small synthetic inputs.
  - `golden/` — expected `*_filled.csv` and decoded reports.
- `.coveragerc` — omit `run_gui`, all `if __name__ == "__main__"` blocks, and the
  `serial`-only code in `sd_download.py`.
- `.github/workflows/tests.yml` — Python 3.11–3.14 matrix; install both requirements
  files; `pytest --cov`; print coverage. Separate **optional** jobs (allowed to
  fail / manually triggered) for `arduino-cli compile` and the case smoke test.
- `CONTRIBUTING.md` — replace "Run the relevant Python script against the `.example`
  fixtures" with `pip install -r requirements-dev.txt && pytest`.

---

## 5. Refactoring for testability

Small, behaviour-preserving changes done alongside the tests that cover them.

### 5.1 `build_gradebook.py` — split `main()`

`main()` currently parses args, reads four files, runs the whole matching/scoring
algorithm in nested closures, prints a report, and writes a file. Split into:

- `parse_args(argv) -> Namespace`
- `build(canvas_path, attendance_path, roster, aliases, session) -> Result`
  where `Result` is a dataclass: `rows_out`, `present/late/absent`, `unmatched`,
  `ambiguous`, `unregistered`, `unsynced`, `target_header`.
- `render_report(result) -> str`
- `write_output(path, rows)`

Lift `match_row` to module scope (take an explicit `CanvasIndex` — `by_login`,
`by_norm`, `student_rows`, `rows`, `c_student` — instead of closing over `main`'s
locals). Tests then assert on `Result` fields instead of scraping stdout.

### 5.2 `register_cards.py` — lift the state machine out of tkinter

Extract from `on_return`:

- `classify_scan(raw) -> ("bad", None) | ("ok", card_id)`
- `resolve_tap(roster, K, card_id) -> ("already", name) | ("new", token)`
- `prepare_save(raw_name) -> str | None`  (trim, cap at 39 chars, reject empty)

`on_return` becomes glue calling these. The `"0000000000"` sentinel check moves
into `classify_scan`.

### 5.3 `decode_attendance.py` — return instead of only printing

`main()` is already thin; add `run(attendance, roster, key, out) -> (scanned,
unknown, registered)` and have `main()` print from that.

### 5.4 `sd_download.py` — separate parsing from the port

Extract `parse_dump(lines) -> list[str]` and `parse_count(lines) -> int | None`
from the serial loops. `main()` keeps all `serial` calls and feeds
`ser`-derived line iterators to the pure parsers.

### 5.5 firmware — extract an Arduino-free crypto header

Move `uidToKey`, `toHex`, `hexToBytes`, `deriveKeysFrom`, `computeToken`,
`decryptNameWith` into `firmware/attendance_reader_PN532/crypto.hpp` depending
only on `mbedtls/*` (no `Arduino.h`, no `String`). The `.ino` `#include`s it; a
native test binary (5.x, Phase 5) links the same header.

### 5.6 `attendance_crypto.py` — minor

Use a `with` block in `load_or_create_key` (currently leaks the read handle).
Move the `__main__` body into `_cli()`. No API change.

---

## 6. Phases

### Phase 0 — Infrastructure
Everything in §4. CI goes green with a single trivial test. No production code
touched.

### Phase 1 — Crypto unit + contract tests
`tests/test_attendance_crypto.py`:

- **KAT, must match the firmware** (`cryptoSelfTest()` in the `.ino`): key
  `00,01,…,1f`; `token(K, "0984257796") == "f989b34da0e80527fc371aabb3ac7402"`;
  `decrypt_name(K, "000102…0e0f" + "bc2085cdcb6691b378e61607857a54e4") ==
  "Michael Hilton"`.
- Roundtrip property: `decrypt_name(K, encrypt_name(K, s)) == s` for ASCII,
  Unicode, `""`, and a 39-char name.
- `token`: deterministic; distinct ids → distinct tokens; changes with the key;
  always 32 lowercase hex.
- `subkeys`: `kmac != kenc`; stable for a given `K`.
- `load_or_create_key`: creates a 64-hex file at mode `0600`; **idempotent**
  (second call returns the same bytes, file not rewritten); rejects a 32-hex file;
  tolerates a trailing newline.
- PKCS7: a full 16-byte pad is added when `len(plaintext) % 16 == 0`; `_unpkcs7`
  rejects `pad == 0`, `pad > 16`, and a corrupted pad trailer.
- `decrypt_name` failure paths: odd-length hex, ciphertext shorter than one block,
  wrong key → `ValueError("bad padding")`.
- `firmware_key_snippet`: 32 `0x??` bytes, contains `#pragma once` and
  `SECRET_KEY[32]`.

`tests/test_crypto_contract.py`:

- Every row of `tests/fixtures/crypto_vectors.json` reproduced by
  `attendance_crypto`.
- Parse the literals out of `attendance_reader_PN532.ino` (`cryptoSelfTest`) and
  assert they equal the fixture. Drift on either side fails.

### Phase 2 — Pure helpers (no refactor required)
- `tests/test_gradebook_helpers.py` — `norm_tokens` (order independence, punctuation
  → space, dedupe), `fmt_points` (`1.0→"1"`, `0.5→"0.5"`, near-integer tolerance,
  trailing-zero strip), `col_label` (`"Jan 20 Activity (995978)" → "jan 20
  activity"`), `load_token_names` / `load_aliases` (header rows, blanks,
  decrypt-fail sentinel, missing file).
- `tests/test_decode.py` — `find_token_column`; `read_attendance` for both the
  sheet-export format (has a `token` header) and the device format (`millis,token`),
  including the `time_col` selection branch, the 32-char token filter, short rows,
  and an empty file.
- `tests/test_register_core.py` — `normalize_key` (`"0984257796"` → itself; letters
  / spaces / newlines stripped; `""` → `""`; value ≥ 2³² wraps; leading zeros
  preserved); `load_roster`/`save_roster` roundtrip (sorted by token, header
  written, 32-char filter, missing enc column → `""`); `upsert` (added vs updated,
  returns previous enc, count correct, persisted to disk).

### Phase 3 — Refactor + high-value gradebook tests
Do §5.1–5.4, each landing with its tests:

- `tests/test_gradebook_matching.py` — table over `match_row`: alias → SIS Login
  ID; exact normalized unique; exact but ambiguous (two students same normalized
  name) → `None, "ambiguous"`; subset match (middle initial); superset match;
  nothing → `None, "none"`.
- `tests/test_gradebook_scoring.py` — boundaries at `late_after` and `close`
  (inclusive); late value is `round(full * late_frac, 4)`; earliest tap per token
  wins; two cards → one student keeps the best status by `present>late>absent`
  rank; tap after `close` → absent 0; never-tapped student → absent 0.
- `tests/test_gradebook_columns.py` — exact `col_label` match preferred over
  substring; zero matches → `SystemExit`; multiple → `SystemExit` "ambiguous";
  `Points Possible` missing / non-numeric → default `1.0` with a warning line.
- `tests/test_gradebook_output.py` — every student row padded to at least
  `c_target + 1` cells; **only** the target column changes; total row count and
  identity columns preserved (re-imports cleanly); `unsynced-*` rows counted, not
  scored; wrong-date and malformed-timestamp rows skipped.
- `tests/test_sd_download.py` — `parse_dump` (marker pair, no markers, `<<<BEGIN`
  with no `<<<END`); `parse_count`; `find_port` matching rules.

### Phase 4 — Golden end-to-end
`tests/test_pipeline_e2e.py` with a `simulate_tap(K, card_id, when)` helper that
reproduces the firmware's `uidToKey` + `computeToken` + `"%Y-%m-%d %H:%M:%S,token"`
log line (this helper is also the firmware oracle). Flow:

1. `load_or_create_key` in a tmp dir.
2. `register_cards` core builds `roster.csv` for a few students.
3. Simulate a class: on-time taps, a late tap, an after-close tap, an unregistered
   card, an `unsynced-` row.
4. `decode_attendance.run(...)` → assert the report.
5. `build_gradebook.build(...)` against `tests/fixtures/Grades.csv` (shaped like
   `Grades.csv.example`) → assert the filled CSV **byte-for-byte** against
   `tests/fixtures/golden/Grades_filled.csv` and every `Result` count.

A `--update-golden` pytest flag (in `conftest.py`) regenerates the golden files.

### Phase 5 — Firmware crypto (gated)
- **Contract test** already landed in Phase 1 — keep it as the always-on guard.
- **Native KAT binary** (`needs_mbedtls`): after §5.5, a `tests/native/` `g++`
  target links `crypto.hpp` against system `libmbedcrypto` and asserts the same
  `crypto_vectors.json`. `pytest` shells out to build+run it; skips cleanly if no
  compiler or mbedTLS.
- **`arduino-cli compile`** — optional CI job, `--fqbn esp32:esp32:esp32`, catches
  syntax/API breakage in the full sketch. Slow (board package download); not on the
  critical path.

### Phase 6 — Case generator (gated, low priority)
`tests/test_case_gen.py`, marked `needs_trimesh`: run `case_gen.py` in a tmp cwd,
assert the three STLs are written and `trimesh.load(...).is_watertight` for each,
and that each mesh's bounding box is within tolerance of a recorded baseline.

---

## 7. Coverage target

~90% line coverage on `attendance_crypto.py`, `build_gradebook.py`,
`decode_attendance.py`, and the `register_cards.py` core. `run_gui`, `__main__`
blocks, and `serial` I/O are excluded via `.coveragerc`, not counted against the
target. CI fails under the threshold once Phase 3 lands.

---

## 8. Latent issues these tests will pin

Not fixed as part of test setup — but each gets a test documenting current
behaviour so a later fix is a deliberate, visible change:

- **`build_gradebook.py` — student-row detection by `"@" in SIS Login ID`**
  (`build_gradebook.py:143`, also in `ROADMAP.md`). An export with a bare Andrew ID
  there yields "0 enrolled" and marks everyone absent, silently.
- **`decode_attendance.py:62`** — a single-column sheet export makes
  `time_col == tok_col`, so the report's time field is the token.
- **`attendance_crypto.py:27`** — `open(path)` read handle is never closed
  (fixed in §5.6).

---

## 9. Sequencing

Phases 0–2 need **no** production changes and cover the crypto contract — do them
first. Phase 3 is where the refactor and the real gradebook payoff land. Phases
4–6 build on that. Each phase leaves CI green.
