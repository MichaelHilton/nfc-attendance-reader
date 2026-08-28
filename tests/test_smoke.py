"""Phase 0 smoke test: the harness is wired up.

Confirms pytest's `pythonpath` reaches software/ and that the shared fixtures
load. Real coverage starts in Phase 1 (test_attendance_crypto.py).
"""


def test_software_dir_on_path():
    import attendance_crypto  # noqa: F401  -- import is the assertion


def test_kat_key_fixture(kat_key):
    assert kat_key == bytes(range(32))
    assert kat_key.hex() == "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"


def test_crypto_vectors_fixture(crypto_vectors):
    assert crypto_vectors["key_hex"] == bytes(range(32)).hex()
    assert any(t["firmware_selftest"] for t in crypto_vectors["tokens"])
    assert any(d["firmware_selftest"] for d in crypto_vectors["decrypt"])
