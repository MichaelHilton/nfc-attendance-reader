// Native known-answer check for firmware/attendance_reader_PN532/crypto.hpp.
//
// Links the actual firmware crypto header against host mbedTLS and verifies the
// vectors in tests/fixtures/crypto_vectors.json. Built and run by
// tests/test_firmware_crypto_native.py, which generates _vectors_gen.h from that
// JSON and skips the whole thing when there is no C++ compiler or mbedTLS.
#include <cstdio>
#include <cstring>

#include "crypto.hpp"
#include "_vectors_gen.h"

static int failures = 0;

static void check(const char* what, bool ok) {
  std::printf("  %-28s %s\n", what, ok ? "ok" : "FAIL");
  if (!ok) ++failures;
}

static void hex_to_key(const char* hex, uint8_t* out, int n) {
  for (int i = 0; i < n; i++) {
    unsigned v = 0;
    std::sscanf(hex + 2 * i, "%2x", &v);
    out[i] = (uint8_t)v;
  }
}

int main() {
  uint8_t K[32];
  hex_to_key(VEC_KEY_HEX, K, 32);
  uint8_t km[32], ke[32];
  deriveKeysFrom(K, km, ke);

  for (int i = 0; i < N_TOKENS; i++) {
    char tok[33];
    computeToken(km, TOKEN_IDS[i], tok);
    check(TOKEN_IDS[i], std::strcmp(tok, TOKEN_HEX[i]) == 0);
  }

  for (int i = 0; i < N_DEC; i++) {
    char name[64];
    bool ok = decryptNameWith(ke, DEC_ENC[i], name, sizeof(name));
    check(DEC_PT[i], ok && std::strcmp(name, DEC_PT[i]) == 0);
  }

  // uidToKey: the DESIGN_NOTES section 2 example, 04 95 AA 3A CF 22 90.
  uint8_t uid[7] = {0x04, 0x95, 0xAA, 0x3A, 0xCF, 0x22, 0x90};
  char id[16];
  uidToKey(uid, 7, id);
  check("uidToKey 04 95 AA 3A ...", std::strcmp(id, "0984257796") == 0);

  std::printf("%s (%d failure%s)\n", failures ? "FAILED" : "OK",
              failures, failures == 1 ? "" : "s");
  return failures ? 1 : 0;
}
