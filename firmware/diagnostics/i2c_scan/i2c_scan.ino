/*
 * I2C scanner — lists every device answering on the bus.
 * Wiring: same as the reader — SDA->IO21, SCL->IO22 (default ESP32 I2C).
 * Upload, open Serial Monitor @ 115200.
 *
 * Read the result:
 *   - "Found 0x24"  -> the PN532 is talking! Wiring/DIP are fine; the issue is
 *                      elsewhere (re-flash the main sketch).
 *   - "Found 0x5D" or 0x14 only -> that's the touch chip; the I2C bus works but
 *                      the PN532 isn't answering -> its DIP switch (must be I2C)
 *                      or an SDA/SCL solder joint.
 *   - "No I2C devices found" -> SDA/SCL not connected (cold joint / swapped / bridge).
 */
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(500);
  Wire.begin();                     // ESP32 default SDA=21, SCL=22 (CN1)
  Serial.println("\nI2C scanner ready. (PN532 should appear at 0x24)");
}

void loop() {
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("Found device at 0x%02X\n", a);
      n++;
    }
  }
  if (n == 0) Serial.println("No I2C devices found — check SDA/SCL wiring & DIP=I2C");
  else        Serial.printf("%d device(s) found.\n", n);
  Serial.println("---");
  delay(2000);
}
