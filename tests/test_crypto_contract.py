"""Phase 1 — the laptop/firmware crypto contract.

Two halves, both driven by tests/fixtures/crypto_vectors.json:

  1. software/attendance_crypto.py reproduces every vector.
  2. The firmware source still carries the literals for the vectors marked
     `firmware_selftest` (attendance_reader_PN532.ino :: cryptoSelfTest).

Editing one side without the other fails here. See docs/TESTING_PLAN.md section 1.
"""
import pathlib

import pytest

import attendance_crypto as ac

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
FIRMWARE_INO = REPO_ROOT / "firmware" / "attendance_reader_PN532" / "attendance_reader_PN532.ino"


@pytest.fixture
def key(crypto_vectors) -> bytes:
    return bytes.fromhex(crypto_vectors["key_hex"])


# ------------------------- half 1: Python side -------------------------
def test_python_reproduces_subkeys(key, crypto_vectors):
    kmac, kenc = ac.subkeys(key)
    assert kmac.hex() == crypto_vectors["subkeys"]["kmac_hex"]
    assert kenc.hex() == crypto_vectors["subkeys"]["kenc_hex"]


def test_python_reproduces_all_token_vectors(key, crypto_vectors):
    for v in crypto_vectors["tokens"]:
        assert ac.token(key, v["id"]) == v["token"], v["id"]


def test_python_reproduces_all_decrypt_vectors(key, crypto_vectors):
    for d in crypto_vectors["decrypt"]:
        assert ac.decrypt_name(key, d["enc_hex"]) == d["plaintext"]


# ------------------------ half 2: firmware side -----------------------
def test_fixture_has_firmware_selftest_rows(crypto_vectors):
    # Guards against the firmware-literal checks below passing vacuously.
    assert any(v["firmware_selftest"] for v in crypto_vectors["tokens"])
    assert any(d["firmware_selftest"] for d in crypto_vectors["decrypt"])


def test_firmware_uses_the_kat_key(crypto_vectors):
    src = FIRMWARE_INO.read_text()
    # cryptoSelfTest builds the master key as bytes 0x00..0x1f: `TK[i] = i`.
    assert "TK[i] = i" in src
    assert crypto_vectors["key_hex"] == bytes(range(32)).hex()


def test_firmware_source_carries_selftest_token_literals(crypto_vectors):
    src = FIRMWARE_INO.read_text()
    for v in crypto_vectors["tokens"]:
        if v["firmware_selftest"]:
            assert v["id"] in src, f"firmware missing id literal {v['id']}"
            assert v["token"] in src, f"firmware missing token literal {v['token']}"


def test_firmware_source_carries_selftest_decrypt_literals(crypto_vectors):
    src = FIRMWARE_INO.read_text()
    for d in crypto_vectors["decrypt"]:
        if d["firmware_selftest"]:
            assert d["enc_hex"] in src, "firmware missing AES ciphertext literal"
            assert d["plaintext"] in src, "firmware missing AES plaintext literal"
