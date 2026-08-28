"""Phase 1 — unit tests for software/attendance_crypto.py.

The known-answer vectors here are the same ones the firmware checks at boot
(cryptoSelfTest in attendance_reader_PN532.ino). If these change, the device and
the laptop tools have diverged. test_crypto_contract.py enforces the other half
of that (the firmware source still carries the matching literals).
"""
import os
import stat

import pytest

import attendance_crypto as ac

FIRMWARE_ENC_HEX = "000102030405060708090a0b0c0d0e0fbc2085cdcb6691b378e61607857a54e4"


# --------------------------- known-answer vectors ---------------------------
def test_token_matches_firmware_selftest(kat_key):
    assert ac.token(kat_key, "0984257796") == "f989b34da0e80527fc371aabb3ac7402"


def test_decrypt_matches_firmware_selftest(kat_key):
    assert ac.decrypt_name(kat_key, FIRMWARE_ENC_HEX) == "Michael Hilton"


def test_subkeys_match_fixture(kat_key, crypto_vectors):
    kmac, kenc = ac.subkeys(kat_key)
    assert kmac.hex() == crypto_vectors["subkeys"]["kmac_hex"]
    assert kenc.hex() == crypto_vectors["subkeys"]["kenc_hex"]


def test_all_token_vectors(kat_key, crypto_vectors):
    for v in crypto_vectors["tokens"]:
        assert ac.token(kat_key, v["id"]) == v["token"], v["id"]


def test_all_decrypt_vectors(kat_key, crypto_vectors):
    for d in crypto_vectors["decrypt"]:
        assert ac.decrypt_name(kat_key, d["enc_hex"]) == d["plaintext"]


# ------------------------------ roundtrip ----------------------------------
@pytest.mark.parametrize(
    "name",
    [
        "Michael Hilton",
        "José García-López",
        "name, with comma",
        "x",
        "N" * 39,          # the device name buffer is 39 chars
        "emoji 🎓 ok",
        "  leading/trailing spaces  ",
    ],
)
def test_encrypt_decrypt_roundtrip(kat_key, name):
    assert ac.decrypt_name(kat_key, ac.encrypt_name(kat_key, name)) == name


def test_encrypt_uses_random_iv(kat_key):
    a = ac.encrypt_name(kat_key, "Alice")
    b = ac.encrypt_name(kat_key, "Alice")
    assert a != b                                  # different IV each call
    assert ac.decrypt_name(kat_key, a) == ac.decrypt_name(kat_key, b) == "Alice"


def test_ciphertext_shape(kat_key):
    h = ac.encrypt_name(kat_key, "")
    assert len(h) % 2 == 0
    assert len(h) >= 64                            # 16-byte IV + >= 16-byte block
    assert all(c in "0123456789abcdef" for c in h)


# ------------------------------- token ------------------------------------
def test_token_is_deterministic(kat_key):
    assert ac.token(kat_key, "0984257796") == ac.token(kat_key, "0984257796")


def test_token_format(kat_key):
    tok = ac.token(kat_key, "0000000042")
    assert len(tok) == 32
    assert all(c in "0123456789abcdef" for c in tok)


def test_distinct_ids_give_distinct_tokens(kat_key):
    toks = {ac.token(kat_key, f"{i:010d}") for i in range(50)}
    assert len(toks) == 50


def test_token_depends_on_key(kat_key):
    other = bytes([1]) * 32
    assert ac.token(kat_key, "0984257796") != ac.token(other, "0984257796")


# ------------------------------ subkeys -----------------------------------
def test_subkeys_distinct_and_stable(kat_key):
    kmac1, kenc1 = ac.subkeys(kat_key)
    kmac2, kenc2 = ac.subkeys(kat_key)
    assert kmac1 == kmac2 and kenc1 == kenc2
    assert kmac1 != kenc1
    assert len(kmac1) == 32 and len(kenc1) == 32


def test_subkeys_depend_on_master_key(kat_key):
    kmac_a, kenc_a = ac.subkeys(kat_key)
    kmac_b, kenc_b = ac.subkeys(bytes([9]) * 32)
    assert kmac_a != kmac_b and kenc_a != kenc_b


# ------------------------- load_or_create_key ----------------------------
def test_creates_key_file_with_restrictive_mode(tmp_path):
    p = tmp_path / "secret.key"
    K = ac.load_or_create_key(str(p))
    assert len(K) == 32
    text = p.read_text()
    assert len(text) == 64 and bytes.fromhex(text) == K
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_load_or_create_key_is_idempotent(tmp_path):
    p = tmp_path / "secret.key"
    first = ac.load_or_create_key(str(p))
    before = p.read_text()
    second = ac.load_or_create_key(str(p))
    assert first == second
    assert p.read_text() == before                 # not rewritten


def test_loads_existing_key(key_file, kat_key):
    assert ac.load_or_create_key(str(key_file)) == kat_key


def test_tolerates_trailing_whitespace(tmp_path, kat_key):
    p = tmp_path / "secret.key"
    p.write_text(kat_key.hex() + "\n  ")
    assert ac.load_or_create_key(str(p)) == kat_key


def test_rejects_wrong_length_key(tmp_path):
    p = tmp_path / "secret.key"
    p.write_text("00" * 16)                         # 16 bytes, not 32
    with pytest.raises(ValueError):
        ac.load_or_create_key(str(p))


def test_rejects_non_hex_key(tmp_path):
    p = tmp_path / "secret.key"
    p.write_text("zz" * 32)
    with pytest.raises(ValueError):                 # binascii.Error subclasses ValueError
        ac.load_or_create_key(str(p))


# ------------------------------- PKCS7 -----------------------------------
def test_pkcs7_adds_full_block_when_aligned():
    padded = ac._pkcs7(b"A" * 16)
    assert len(padded) == 32
    assert padded[16:] == bytes([16]) * 16


def test_pkcs7_pads_partial_block():
    assert ac._pkcs7(b"A" * 15) == b"A" * 15 + b"\x01"
    assert ac._pkcs7(b"") == bytes([16]) * 16


@pytest.mark.parametrize("n", [0, 1, 15, 16, 17, 31, 32])
def test_pkcs7_roundtrip(n):
    data = b"x" * n
    assert ac._unpkcs7(ac._pkcs7(data)) == data


@pytest.mark.parametrize(
    "bad",
    [
        b"abc\x00",                # pad byte 0
        b"abc\x11",                # pad byte 17 (> 16)
        b"AAAA\x03\x03\x02",       # inconsistent trailer
    ],
)
def test_unpkcs7_rejects_bad_padding(bad):
    with pytest.raises(ValueError):
        ac._unpkcs7(bad)


# ------------------------- decrypt_name failures ------------------------
def test_decrypt_rejects_odd_length_hex(kat_key):
    with pytest.raises(ValueError):
        ac.decrypt_name(kat_key, "abc")


def test_decrypt_rejects_non_block_aligned_ciphertext(kat_key):
    with pytest.raises(ValueError):
        ac.decrypt_name(kat_key, "00" * 20)        # 16-byte IV + 4-byte "ciphertext"


def test_decrypt_with_wrong_key_raises(kat_key):
    # Fixed ciphertext + fixed wrong key => deterministic: PKCS7 unpad fails.
    with pytest.raises(ValueError):
        ac.decrypt_name(bytes([1]) * 32, FIRMWARE_ENC_HEX)


def test_decrypt_empty_ciphertext_current_behavior(kat_key):
    # Documents a rough edge: an IV with no ciphertext trips _unpkcs7's b[-1]
    # rather than raising a clean ValueError. Change this test deliberately if
    # decrypt_name grows a guard.
    with pytest.raises(IndexError):
        ac.decrypt_name(kat_key, "00" * 16)


# --------------------------- firmware snippet --------------------------
def test_firmware_key_snippet_structure(kat_key):
    import re

    snip = ac.firmware_key_snippet(kat_key)
    assert "#pragma once" in snip
    assert "SECRET_KEY[32]" in snip
    assert snip.endswith("\n")
    found = re.findall(r"0x[0-9a-f]{2}", snip)
    assert len(found) == 32
    assert bytes(int(h, 16) for h in found) == kat_key
