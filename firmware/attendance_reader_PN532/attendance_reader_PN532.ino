/*
 * Classroom Attendance Reader — 3.5" CYD + PN532 (fast/responsive build)
 * -----------------------------------------------------------------------------
 * Board : ESP32-3248S035C  (Sunton CYD, 3.5" ST7796 screen, ESP32-WROOM-32)
 * Reader: PN532 NFC (13.56 MHz) over I2C — reads the card UID
 * Sound : small 8ohm speaker on the "SPEAK" connector (GPIO26) — optional
 *
 * Libraries (Library Manager): "TFT_eSPI" (Bodmer), "Adafruit PN532" (+ Adafruit BusIO)
 * Wiring: PN532 VCC->3V3, GND->GND, SDA->IO21, SCL->IO22 (CN1); DIP switches = I2C.
 * PRIVACY: card numbers are NEVER stored. roster.csv holds (token,enc_name) where
 *   token   = HMAC-SHA256(secret, id)[:16]   (one-way; can't recover the card number)
 *   enc_name= AES-256-CBC(secret, name)      (device decrypts to show the name)
 *   attendance.csv = (timestamp,token) — stored locally only; WiFi is used just for NTP time.
 * Build roster.csv with register_cards.py; decode attendance with decode_attendance.py.
 * TIP: bump SPI_FREQUENCY to 40000000 in TFT_eSPI User_Setup.h for faster draws.
 * -----------------------------------------------------------------------------
 */

#include <WiFi.h>
#include <time.h>
#include <SPI.h>
#include <SD.h>
#include <Wire.h>
#include <Adafruit_PN532.h>
#include <TFT_eSPI.h>
#include "mbedtls/md.h"
#include "mbedtls/aes.h"
#include "crypto.hpp"   // uidToKey / deriveKeysFrom / computeToken / decryptNameWith
                        // (shared byte-for-byte with software/attendance_crypto.py)

// ------------------------------ USER SETTINGS -------------------------------
// WiFi credentials live in wifi_config.h (kept out of version control via
// .gitignore) so real credentials never sit in the tracked sketch. If that file
// is missing the sketch still compiles with the placeholders below — put your
// network in wifi_config.h, not here.
#if __has_include("wifi_config.h")
  #include "wifi_config.h"
#endif
#ifndef WIFI_SSID
  #define WIFI_SSID "YOUR_WIFI_SSID"
#endif
#ifndef WIFI_PASS
  #define WIFI_PASS "YOUR_WIFI_PASSWORD"
#endif
// WiFi is used ONLY to set the clock over NTP (no cloud upload). TZ = US Eastern (Pittsburgh).
const char* NTP1    = "pool.ntp.org";
const char* NTP2    = "time.nist.gov";
const char* TZ_INFO = "EST5EDT,M3.2.0,M11.1.0";

// --- SECRET KEY lives in secret_key.h (kept out of version control via
// .gitignore, same pattern as wifi_config.h above), never in this tracked file.
// Run `python3 attendance_crypto.py` from software/ — it writes secret_key.h
// directly into this sketch folder. If that file is missing, the sketch still
// compiles using the placeholder key below, but tokens/names won't match any
// real roster until you generate and drop in the real one. ---
#if __has_include("secret_key.h")
  #include "secret_key.h"
#else
  static const uint8_t SECRET_KEY[32] = {
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f
  };  // <-- placeholder only. Never used for a real roster.
#endif
uint8_t KMAC[32], KENC[32];

#define PN532_IRQ   255
#define PN532_RESET 255
#define SD_SCK  18
#define SD_MISO 19
#define SD_MOSI 23
#define SD_CS    5
#define SPEAKER_PIN 26

const unsigned long COOLDOWN_MS = 3000;   // ignore same card again within 3 s
const unsigned long RESULT_MS   = 1500;   // how long the name stays on screen
#define MAX_STUDENTS 300
// ----------------------------------------------------------------------------

TFT_eSPI        tft = TFT_eSPI();
SPIClass        sdSPI(VSPI);
Adafruit_PN532  nfc(PN532_IRQ, PN532_RESET);

struct Entry { char token[33]; char enc[130]; };   // HMAC token + AES-encrypted name (hex)
Entry roster[MAX_STUDENTS];
int   rCount = 0;

char          lastUid[15] = {0};
unsigned long lastTagTime = 0;
unsigned long resultUntil = 0;
bool          showingResult = false;
bool          sdOK = false, nfcOK = false;


// ------------------------------- helpers ------------------------------------
int cmpEntry(const void* a, const void* b) {
  return strcmp(((const Entry*)a)->token, ((const Entry*)b)->token);
}

// ------------------------------- crypto -------------------------------------
// The primitives (uidToKey / sha256 / hmac256 / toHex / hexToBytes /
// deriveKeysFrom / computeToken / decryptNameWith) live in crypto.hpp so the
// host test suite can link and check them. The two thin wrappers below bind
// them to this sketch's globals (SECRET_KEY, KMAC, KENC).
void deriveKeys() { deriveKeysFrom(SECRET_KEY, KMAC, KENC); }

bool decryptName(const char* encHex, char* out, size_t outsz) {
  return decryptNameWith(KENC, encHex, out, outsz);
}
// Prove mbedTLS matches the laptop tools using a fixed test vector (key = 00..1f).
void cryptoSelfTest() {
  uint8_t TK[32]; for (int i = 0; i < 32; i++) TK[i] = i;
  uint8_t km[32], ke[32]; deriveKeysFrom(TK, km, ke);
  uint8_t mac[32]; hmac256(km, 32, (const uint8_t*)"0984257796", 10, mac);
  char hx[33]; toHex(mac, 16, hx);
  bool tOK = (strcmp(hx, "f989b34da0e80527fc371aabb3ac7402") == 0);
  char nm[40];
  bool aOK = decryptNameWith(ke,
    "000102030405060708090a0b0c0d0e0fbc2085cdcb6691b378e61607857a54e4", nm, sizeof(nm))
    && strcmp(nm, "Michael Hilton") == 0;
  Serial.printf("crypto self-test: HMAC %s, AES %s\n", tOK ? "OK" : "FAIL", aOK ? "OK" : "FAIL");
}

// Redraw ONLY the center text band (much faster than fillScreen).
void drawStatus(const char* big, const char* small, uint16_t color) {
  int cy = tft.height() / 2;
  tft.fillRect(0, cy - 70, tft.width(), 140, TFT_BLACK);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(color, TFT_BLACK);
  tft.setTextSize(3);
  tft.drawString(big, tft.width() / 2, cy - 20);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.setTextSize(2);
  tft.drawString(small, tft.width() / 2, cy + 26);
}

void beepKnown()   { tone(SPEAKER_PIN, 2000, 120); }   // short high ding
void beepUnknown() { tone(SPEAKER_PIN, 350, 250);  }   // low buzz

// ------------------------------- roster -------------------------------------
void loadRoster() {
  rCount = 0;
  if (!sdOK) return;
  File f = SD.open("/roster.csv");
  if (!f) return;
  while (f.available() && rCount < MAX_STUDENTS) {
    String line = f.readStringUntil('\n');
    line.trim();
    if (line.length() == 0) continue;
    int c = line.indexOf(',');
    if (c < 0) continue;
    String tk = line.substring(0, c);  tk.trim();
    String en = line.substring(c + 1); en.trim();
    if (tk.length() != 32) continue;                            // skip header / bad rows (token = 32 hex)
    strncpy(roster[rCount].token, tk.c_str(), 32); roster[rCount].token[32] = 0;
    strncpy(roster[rCount].enc,   en.c_str(), sizeof(roster[rCount].enc) - 1);
    roster[rCount].enc[sizeof(roster[rCount].enc) - 1] = 0;
    rCount++;
  }
  f.close();
  qsort(roster, rCount, sizeof(Entry), cmpEntry);               // sort for bsearch
}

const Entry* lookupToken(const char* token) {
  Entry key; strncpy(key.token, token, 32); key.token[32] = 0;
  return (const Entry*)bsearch(&key, roster, rCount, sizeof(Entry), cmpEntry);
}

// Local timestamp "YYYY-MM-DD HH:MM:SS" from NTP; "unsynced-<millis>" until the clock is set.
void getTimestamp(char* out, size_t n) {
  struct tm t;
  if (getLocalTime(&t, 50) && (t.tm_year + 1900) >= 2024) {
    strftime(out, n, "%Y-%m-%d %H:%M:%S", &t);
  } else {
    snprintf(out, n, "unsynced-%lu", (unsigned long)millis());
  }
}

void logToSD(const char* token) {                               // attendance stores timestamp + token
  if (!sdOK) return;
  char ts[32]; getTimestamp(ts, sizeof(ts));
  File f = SD.open("/attendance.csv", FILE_APPEND);
  if (f) { f.printf("%s,%s\n", ts, token); f.close(); }
}

// ---------- serial commands over USB (dump / roster / count / help) ----------
// Print a file wrapped in markers the Python downloader looks for.
void dumpFile(const char* path, const char* label) {
  Serial.printf("<<<BEGIN %s>>>\n", label);
  if (!sdOK) { Serial.println("(no SD card)"); }
  else {
    File f = SD.open(path);
    if (!f) Serial.println("(file not found)");
    else { while (f.available()) Serial.write(f.read()); f.close(); }
  }
  Serial.printf("\n<<<END %s>>>\n", label);
}

void handleSerial() {
  static char cmd[16]; static int n = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (n == 0) continue;
      cmd[n] = 0; n = 0;
      if      (!strcasecmp(cmd, "dump"))   dumpFile("/attendance.csv", "attendance.csv");
      else if (!strcasecmp(cmd, "roster")) dumpFile("/roster.csv", "roster.csv");
      else if (!strcasecmp(cmd, "count")) {
        int rows = -1;
        if (sdOK) { File f = SD.open("/attendance.csv"); if (f) { rows = 0; while (f.available()) if (f.read() == '\n') rows++; f.close(); } }
        Serial.printf("attendance rows: %d\n", rows > 0 ? rows - 1 : 0);   // minus header
      }
      else if (!strcasecmp(cmd, "help") || !strcmp(cmd, "?"))
        Serial.println("Commands: dump | roster | count | help");
      else Serial.printf("? unknown '%s' (try 'help')\n", cmd);
    } else if (n < 15) cmd[n++] = c;
  }
}

// --------------------------------- setup ------------------------------------
void setup() {
  Serial.begin(115200);
  deriveKeys();          // derive KMAC/KENC from SECRET_KEY
  cryptoSelfTest();      // prints HMAC/AES OK|FAIL — must be OK for the roster to match

  tft.init();
  tft.setRotation(1);   // board mounted rotated 180 deg (cable exits bottom-left)
  tft.fillScreen(TFT_BLACK);
  drawStatus("Booting", "please wait", TFT_WHITE);

  sdSPI.begin(SD_SCK, SD_MISO, SD_MOSI, SD_CS);
  sdOK = SD.begin(SD_CS, sdSPI);
  if (sdOK && !SD.exists("/attendance.csv")) {
    File f = SD.open("/attendance.csv", FILE_WRITE);
    if (f) { f.println("timestamp,token"); f.close(); }
  }
  loadRoster();

  Wire.begin();
  delay(50);
  nfc.begin();
  uint32_t ver = 0;                          // retry: PN532 can be slow/mid-state after a reset
  for (int i = 0; i < 12 && ver == 0; i++) { ver = nfc.getFirmwareVersion(); if (!ver) delay(100); }
  nfcOK = (ver != 0);
  if (nfcOK) {
    nfc.SAMConfig();
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);          // connects in the background (for NTP only)
  configTzTime(TZ_INFO, NTP1, NTP2);         // set the clock over NTP once WiFi is up

  char note[40];
  if (!nfcOK)       strcpy(note, "PN532 not found-check wiring/DIP");
  else if (!sdOK)   strcpy(note, "WARNING: no SD card");
  else              snprintf(note, sizeof(note), "%d in roster", rCount);
  drawStatus(nfcOK ? "Ready" : "Reader?", note,
             nfcOK ? (sdOK ? TFT_GREEN : TFT_ORANGE) : TFT_RED);
  tone(SPEAKER_PIN, 1200, 80);               // boot blip
  Serial.println("Serial commands: dump | roster | count | help");
}

// --------------------------------- loop -------------------------------------
void loop() {
  handleSerial();                            // USB commands: dump the SD files, etc.

  // clear the result back to "Ready" on a timer — no blocking delay
  if (showingResult && (long)(millis() - resultUntil) >= 0) {
    drawStatus("Ready", "tap your card", TFT_GREEN);
    showingResult = false;
  }
  if (!nfcOK) { delay(200); return; }

  uint8_t uid[7]; uint8_t len = 0;
  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &len, 300)) {
    char id[15]; uidToKey(uid, len, id);      // 10-digit card id (never stored)
    unsigned long now = millis();
    if (strcmp(id, lastUid) == 0 && (now - lastTagTime) < COOLDOWN_MS) return;
    strncpy(lastUid, id, 15);  lastUid[14] = 0;
    lastTagTime = now;

    char token[33]; computeToken(KMAC, id, token);  // keyed one-way token
    const Entry* e = lookupToken(token);
    char name[40];
    bool known = (e != NULL) && decryptName(e->enc, name, sizeof(name));
    Serial.printf("Card token %s -> %s\n", token, known ? name : "UNKNOWN");

    logToSD(token);                           // attendance stores timestamp + token (local, no cloud)

    if (known) { beepKnown();   drawStatus(name, sdOK ? "saved" : "no SD", TFT_CYAN); }
    else       { beepUnknown(); drawStatus("Unknown", "not registered", TFT_ORANGE); }
    resultUntil = now + RESULT_MS;
    showingResult = true;
  }
}
