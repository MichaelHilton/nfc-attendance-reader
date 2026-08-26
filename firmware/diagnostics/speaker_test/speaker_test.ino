/*
 * Speaker bench test — beeps on GPIO26 (the CYD "SPEAK" amp) in a loop.
 * Plug the speaker into the SPEAK connector, upload, and you should hear
 * two alternating tones once per second. No screen/SD/reader needed.
 */
#define SPEAKER_PIN 26

void setup() {
  Serial.begin(115200);
  Serial.println("Speaker test: you should hear alternating beeps.");
}

void loop() {
  tone(SPEAKER_PIN, 2000, 200);   // high
  delay(600);
  tone(SPEAKER_PIN, 1000, 200);   // low
  delay(600);
}
