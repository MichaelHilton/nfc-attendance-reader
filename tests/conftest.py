"""Shared pytest fixtures for the attendance-reader test suite.

`software/` is placed on sys.path via pyproject.toml (`pythonpath`), so tests can
`import attendance_crypto as ac` the same way the scripts import each other.
"""
import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden", action="store_true", default=False,
        help="rewrite the committed golden files in tests/fixtures/ from current output",
    )


@pytest.fixture
def update_golden(request) -> bool:
    return request.config.getoption("--update-golden")


def assert_golden(path: pathlib.Path, actual: str, update: bool) -> None:
    """Compare `actual` to the golden file at `path`; with `update`, (re)write it."""
    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual)
        return
    assert path.exists(), f"missing golden {path}; run pytest --update-golden"
    assert actual == path.read_text(), f"output drifted from {path}"

# The firmware's crypto self-test vector (attendance_reader_PN532.ino,
# cryptoSelfTest): master key = bytes 0x00..0x1f. Every crypto test that needs a
# fixed, cross-checked key uses this one.
KAT_KEY = bytes(range(32))


@pytest.fixture
def kat_key() -> bytes:
    return KAT_KEY


@pytest.fixture
def crypto_vectors() -> list[dict]:
    """Rows from tests/fixtures/crypto_vectors.json (shared with the firmware
    contract test)."""
    return json.loads((FIXTURES / "crypto_vectors.json").read_text())


@pytest.fixture
def key_file(tmp_path, kat_key) -> pathlib.Path:
    """A secret.key file (hex) holding the KAT key, in an isolated tmp dir."""
    p = tmp_path / "secret.key"
    p.write_text(kat_key.hex())
    return p
