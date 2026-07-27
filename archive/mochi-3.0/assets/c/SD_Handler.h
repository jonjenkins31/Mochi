#ifndef SD_HANDLER_H
#define SD_HANDLER_H

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>

namespace SDHandler {
    File spriteFile;

    void begin(uint8_t csPin) {
        if (!SD.begin(csPin)) {
            Serial.println("SD card initialization failed!");
            while (1);
        }
        Serial.println("SD card initialized.");
    }

    bool openFile(const char* filename) {
        spriteFile = SD.open(filename);
        if (!spriteFile) {
            Serial.println("Failed to open file!");
            return false;
        }
        return true;
    }

    void closeFile() {
        if (spriteFile) {
            spriteFile.close();
        }
    }

    File* getFile() {
        return &spriteFile;
    }
}

#endif // SD_HANDLER_H