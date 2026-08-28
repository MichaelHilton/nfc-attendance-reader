"""Phase 5 — compile firmware/attendance_reader_PN532/crypto.hpp against host
mbedTLS and check it produces the shared crypto vectors.

This is the strongest laptop/firmware guard: it exercises the *actual* firmware
header, not a reimplementation. It is gated on a C++ compiler + mbedTLS being
present (marker: needs_mbedtls) and skips cleanly otherwise, so a normal
`pytest` run is unaffected. CI installs libmbedtls-dev so it runs there.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.needs_mbedtls

HERE = pathlib.Path(__file__).parent
NATIVE = HERE / "native"
FW_DIR = HERE.parent / "firmware" / "attendance_reader_PN532"
VECTORS = HERE / "fixtures" / "crypto_vectors.json"

_MBEDTLS_PREFIXES = (
    "/usr", "/usr/local", "/opt/homebrew",
    "/opt/homebrew/opt/mbedtls", "/opt/homebrew/opt/mbedtls@3", "/opt/homebrew/opt/mbedtls@2",
)


def _compiler():
    for name in ("c++", "g++", "clang++"):
        if shutil.which(name):
            return name
    return None


def _mbedtls_flags():
    """(compile_flags, link_flags) for mbedTLS, or None if it can't be found."""
    if shutil.which("pkg-config"):
        for pkg in ("mbedcrypto", "mbedtls"):
            if subprocess.run(["pkg-config", "--exists", pkg]).returncode == 0:
                cf = subprocess.check_output(["pkg-config", "--cflags", pkg], text=True).split()
                lf = subprocess.check_output(["pkg-config", "--libs", pkg], text=True).split()
                return cf, lf
    for prefix in _MBEDTLS_PREFIXES:
        p = pathlib.Path(prefix)
        if (p / "include" / "mbedtls" / "aes.h").is_file():
            return [f"-I{p}/include"], [f"-L{p}/lib", "-lmbedcrypto"]
    return None


_CANARY = (
    '#include "mbedtls/md.h"\n'
    '#include "mbedtls/aes.h"\n'
    "int main(){ mbedtls_aes_context a; mbedtls_aes_init(&a); mbedtls_aes_free(&a);\n"
    "  return mbedtls_md_info_from_type(MBEDTLS_MD_SHA256) == 0; }\n"
)


def _classic_api_available(cxx, cflags, ldflags, tmp):
    """True if this host's mbedTLS still has the pre-4.x public mbedtls/aes.h +
    mbedtls/md.h API that crypto.hpp uses (ESP32 core and Ubuntu have it;
    Homebrew's mbedTLS 4.x does not)."""
    src = tmp / "canary.cpp"
    src.write_text(_CANARY)
    proc = subprocess.run(
        [cxx, "-std=c++17", *cflags, str(src), *ldflags, "-o", str(tmp / "canary")],
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def _write_vectors_header(dest: pathlib.Path):
    v = json.loads(VECTORS.read_text())
    toks, decs = v["tokens"], v["decrypt"]

    def arr(name, values):
        body = ", ".join('"' + s + '"' for s in values)
        return f"static const char* {name}[] = {{ {body} }};"

    dest.write_text("\n".join([
        "#pragma once",
        "// generated from tests/fixtures/crypto_vectors.json — do not edit",
        f'#define VEC_KEY_HEX "{v["key_hex"]}"',
        arr("TOKEN_IDS", [t["id"] for t in toks]),
        arr("TOKEN_HEX", [t["token"] for t in toks]),
        f"static const int N_TOKENS = {len(toks)};",
        arr("DEC_ENC", [d["enc_hex"] for d in decs]),
        arr("DEC_PT", [d["plaintext"] for d in decs]),
        f"static const int N_DEC = {len(decs)};",
        "",
    ]))


@pytest.fixture(scope="module")
def native_binary(tmp_path_factory):
    cxx = _compiler()
    if not cxx:
        pytest.skip("no C++ compiler on PATH")
    flags = _mbedtls_flags()
    if not flags:
        pytest.skip("mbedTLS headers/libs not found")
    cflags, ldflags = flags

    build_dir = tmp_path_factory.mktemp("native")
    if not _classic_api_available(cxx, cflags, ldflags, build_dir):
        pytest.skip("host mbedTLS lacks the classic mbedtls/aes.h API (mbedTLS >= 4)")

    _write_vectors_header(NATIVE / "_vectors_gen.h")

    binary = build_dir / "crypto_kat"
    cmd = [
        cxx, "-std=c++17", "-O1", "-Wall",
        f"-I{FW_DIR}", f"-I{NATIVE}",
        str(NATIVE / "crypto_kat.cpp"),
        *cflags, "-o", str(binary), *ldflags,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, (
        "crypto.hpp failed to compile/link against host mbedTLS:\n"
        + " ".join(cmd) + "\n" + proc.stdout + proc.stderr
    )
    return binary


def test_firmware_crypto_hpp_matches_vectors(native_binary):
    proc = subprocess.run([str(native_binary)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "FAIL" not in proc.stdout, proc.stdout
