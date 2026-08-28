#pragma once
/*
 * crypto.hpp — the token / name crypto shared by the sketch and the host tests.
 *
 * Arduino-free: depends only on libc + mbedTLS (which the ESP32 core provides,
 * and which host tests link directly). software/attendance_crypto.py must match
 * every function here byte-for-byte — see docs/TESTING_PLAN.md and the boot
 * self-test cryptoSelfTest() in the .ino.
 *
 *   deriveKeysFrom(K)   : km = SHA256("MAC|"+K),  ke = SHA256("ENC|"+K)
 *   computeToken(km,id)  : HMAC-SHA256(km, id)[:16]  -> 32 lowercase hex chars
 *   decryptNameWith(ke,h): AES-256-CBC decrypt of hex(iv[16]+ct), strip PKCS7
 *   uidToKey(uid,len)    : first 4 UID bytes little-endian, "%010lu"
 */
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include "mbedtls/md.h"
#include "mbedtls/aes.h"

// Card key = first 4 UID bytes, little-endian, as a zero-padded 10-digit decimal.
// This matches the USB keyboard-wedge registration reader exactly (e.g. 0984257796),
// so IDs captured at the laptop line up with IDs read here.
static inline void uidToKey(const uint8_t* uid, uint8_t len, char* out) {   // out must hold >=11
  uint32_t v = 0;
  for (uint8_t i = 0; i < 4 && i < len; i++) v |= (uint32_t)uid[i] << (8 * i);
  sprintf(out, "%010lu", (unsigned long)v);
}

static inline void sha256(const uint8_t* in, size_t n, uint8_t out[32]) {
  mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), in, n, out);
}
static inline void hmac256(const uint8_t* key, size_t klen, const uint8_t* in, size_t n, uint8_t out[32]) {
  mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), key, klen, in, n, out);
}
static inline void toHex(const uint8_t* b, int n, char* out) {          // lowercase; out >= 2n+1
  static const char* H = "0123456789abcdef";
  for (int i = 0; i < n; i++) { out[2*i] = H[b[i] >> 4]; out[2*i+1] = H[b[i] & 0xf]; }
  out[2*n] = 0;
}
static inline int hexToBytes(const char* h, uint8_t* out, int maxb) {
  int n = strlen(h) / 2; if (n > maxb) return -1;
  for (int i = 0; i < n; i++) { unsigned v; sscanf(h + 2*i, "%2x", &v); out[i] = (uint8_t)v; }
  return n;
}
// km = SHA256("MAC|" + K),  ke = SHA256("ENC|" + K)
static inline void deriveKeysFrom(const uint8_t* K, uint8_t km[32], uint8_t ke[32]) {
  uint8_t buf[36];
  memcpy(buf, "MAC|", 4); memcpy(buf + 4, K, 32); sha256(buf, 36, km);
  memcpy(buf, "ENC|", 4); memcpy(buf + 4, K, 32); sha256(buf, 36, ke);
}
// token = HMAC-SHA256(kmac, id)[:16] as 32 lowercase hex chars
static inline void computeToken(const uint8_t* kmac, const char* id, char* out33) {
  uint8_t mac[32]; hmac256(kmac, 32, (const uint8_t*)id, strlen(id), mac);
  toHex(mac, 16, out33);
}
// decrypt hex(iv[16] + ciphertext) with a given AES-256 key, strip PKCS7 -> out
static inline bool decryptNameWith(const uint8_t* ke, const char* encHex, char* out, size_t outsz) {
  int blen = strlen(encHex) / 2;
  if (blen < 32 || (blen % 16) != 0 || blen > 160) return false;
  uint8_t raw[160]; if (hexToBytes(encHex, raw, sizeof(raw)) != blen) return false;
  uint8_t iv[16]; memcpy(iv, raw, 16);
  int ctlen = blen - 16;
  uint8_t pt[144];
  mbedtls_aes_context a; mbedtls_aes_init(&a);
  if (mbedtls_aes_setkey_dec(&a, ke, 256) != 0) { mbedtls_aes_free(&a); return false; }
  int rc = mbedtls_aes_crypt_cbc(&a, MBEDTLS_AES_DECRYPT, ctlen, iv, raw + 16, pt);
  mbedtls_aes_free(&a);
  if (rc != 0) return false;
  int pad = pt[ctlen - 1];
  if (pad < 1 || pad > 16 || pad > ctlen) return false;
  int nlen = ctlen - pad;
  if ((size_t)nlen >= outsz) nlen = outsz - 1;
  memcpy(out, pt, nlen); out[nlen] = 0;
  return true;
}
