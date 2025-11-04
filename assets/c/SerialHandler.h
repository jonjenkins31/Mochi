#ifndef SERIALHANDLER_H
#define SERIALHANDLER_H

#include <Arduino.h>


namespace SerialHandler {

  enum MessageType {
    INFO,
    WARNING,
    ERROR,
    STATUS,
    TASK,
    FRAMERATE,
  };

  bool enableErrorMessages = false;
  bool enableStatusMessages = false;
  bool enableTaskMessages = false;
  bool enableFrameRateMessages = false;

  void begin() {
    Serial.begin(115200);
  }

  bool isSerialEstablished() {
      return Serial; // Returns true if the serial connection is established
  }

  String readCommand() {
    if (Serial.available() > 0) {
      String command = Serial.readStringUntil('\n');
      command.trim();
      Serial.println("Received command: " + command);
      return command;
    }
    return "";
  }

  void printMessage(const String &message, MessageType type) {
    switch (type) {
      case ERROR:
        if (enableErrorMessages) {
          Serial.println("ERROR: " + message);
        }
        break;
      case STATUS:
        if (enableStatusMessages) {
          Serial.println("STATUS: " + message);
        }
        break;
      case TASK:
        if (enableTaskMessages) {
          Serial.println("TASK: " + message);
        }
        break;
      case FRAMERATE:
        if (enableFrameRateMessages) {
          Serial.println("FRAMERATE: " + message);
        }
        break;
      default:
        Serial.println("UNKNOWN: " + message);
        break;
    }
  }

  void printInlineMessage(const String& message, MessageType type) {
    switch (type) {
      case INFO:
        Serial.print("INFO: ");
        break;
      case WARNING:
        Serial.print("WARNING: ");
        break;
      case ERROR:
        Serial.print("ERROR: ");
        break;
      case STATUS:
        Serial.print("STATUS: ");
        break;
      case TASK:
        Serial.print("TASK: ");
        break;
      case FRAMERATE:
        Serial.print("FRAMERATE: ");
        break;
      default:
        Serial.print("UNKNOWN: ");
        break;
    }
    Serial.println(message);
  }

  void print(const String &message) {
    Serial.print(message);
  }

  void println(const String &message) {
    Serial.println(message);
  }

  void println() {
    Serial.println();
  }

} // namespace SerialHandler

#endif // SERIALHANDLER_H