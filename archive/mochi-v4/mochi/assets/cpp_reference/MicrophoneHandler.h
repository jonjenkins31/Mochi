#ifndef MICROPHONEHANDLER_H
#define MICROPHONEHANDLER_H

#include <Arduino.h>
#include "SerialHandler.h"

// Define the analog pins
#define MIC1_PIN A17  // Corresponds to pin 40
#define MIC2_PIN A16  // Corresponds to pin 41

#define SAMPLE_RATE 8000  // Desired sampling rate (8 kHz)
#define PLOT_MIN 0.0
#define PLOT_MAX 4095.0

unsigned long lastSampleTime = 0;
const unsigned long sampleInterval = 1000000 / SAMPLE_RATE;  // Interval between samples in microseconds

namespace MicrophoneHandler {

void setup() {
  pinMode(MIC1_PIN, INPUT);
  pinMode(MIC2_PIN, INPUT);
  SerialHandler::printMessage("Microphones initialized", SerialHandler::STATUS);
}

int readMic1() {
  return analogRead(MIC1_PIN);
}

int readMic2() {
  return analogRead(MIC2_PIN);
}

void sendAudioData() {
  unsigned long currentTime = micros();
  if (currentTime - lastSampleTime >= sampleInterval) {
    int mic1Value = readMic1();
    int mic2Value = readMic2();

    // Print the sample values
    Serial.print("Mic1:"); Serial.println(mic1Value);
    Serial.print("Mic2:"); Serial.println(mic2Value);

    // Print min and max values to set the scale
    Serial.print("Min:"); Serial.println(PLOT_MIN);
    Serial.print("Max:"); Serial.println(PLOT_MAX);

    lastSampleTime = currentTime;  // Update the last sample time
  }
}

void testMicrophones() {
  while (true) {
    sendAudioData();
    delay(10);  // Adjust the delay to control the sample rate
  }
}

} // namespace MicrophoneHandler

#endif