/*
 * PN532 bench test — reader only. No display, no SD.
 * Confirms the PN532 is wired right and reads your card's UID.
 *
 * Wiring (jumpers are fine for the bench):
 *   PN532 VCC -> 3V3,  GND -> GND,  SDA -> IO21,  SCL -> IO22   (CN1)
 *   Set the PN532 DIP switches to I2C mode.
 *
 * Library: install "Adafruit PN532" (Library Manager; also installs Adafruit BusIO).
 *
 * Upload, open Serial Monitor @ 115200:
 *   - "PN532 found, firmware 0x..."  -> comms good; tap a card to see its UID.
 *   - "PN532 NOT found"              -> DIP not on I2C, SDA/SCL swapped, or VCC/GND.
 */
#include <Wire.h>
#include <Adafruit_PN532.h>

Adafruit_PN532 nfc(255, 255);   // I2C mode (uses Wire; IRQ/RESET not wired)

void setup() {
  Serial.begin(115200);
  delay(600);
  Wire.begin();                 // ESP32 default I2C pins = 21 (SDA) / 22 (SCL) = CN1
  nfc.begin();

  uint32_t ver = nfc.getFirmwareVersion();
  if (!ver) {
    Serial.println("PN532 NOT found — check: DIP switches = I2C, SDA->IO21, SCL->IO22, VCC->3V3, GND->GND");
    while (1) delay(1000);
  }
  Serial.print("PN532 found, firmware 0x");
  Serial.println(ver, HEX);
  nfc.SAMConfig();
  Serial.println("Tap a card on the PN532...");
}

void loop() {
  uint8_t uid[7]; uint8_t len = 0;
  if (nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &len, 500)) {
    Serial.print("UID: ");
    for (uint8_t i = 0; i < len; i++) {
      if (uid[i] < 0x10) Serial.print('0');
      Serial.print(uid[i], HEX);
    }
    Serial.println();
    delay(800);
  }
}
