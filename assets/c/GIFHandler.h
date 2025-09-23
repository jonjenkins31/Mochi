#ifndef GIF_HANDLER_H
#define GIF_HANDLER_H

#include <Arduino.h>
#include <SmartMatrix.h>
#include <SD.h>
#include <GifDecoder.h>
#include "Filename_Functions.h"

namespace GIFHandler {
    const int DISPLAY_TIME_SECONDS = 10;
    const int NUMBER_FULL_CYCLES = 100;
    const int SD_CS = BUILTIN_SDCARD;
    const char* GIF_DIRECTORY = "/gifs/";

    GifDecoder<kMatrixWidth, kMatrixHeight, 12> decoder;
    int num_files;

    void screenClearCallback() {
        backgroundLayer.fillScreen({0, 0, 0});
    }

    void updateScreenCallback() {
        backgroundLayer.swapBuffers();
    }

    void drawPixelCallback(int16_t x, int16_t y, uint8_t red, uint8_t green, uint8_t blue) {
        backgroundLayer.drawPixel(x, y, {red, green, blue});
    }

    bool checkSDCard() {
        if (initFileSystem(SD_CS) < 0) {
            scrollingLayer.start("No SD card", -1);
            Serial.println("No SD card");
            return false;
        }

        num_files = enumerateGIFFiles(GIF_DIRECTORY, true);
        if (num_files < 0) {
            scrollingLayer.start("No gifs directory", -1);
            Serial.println("No gifs directory");
            return false;
        }

        if (!num_files) {
            scrollingLayer.start("Empty gifs directory", -1);
            Serial.println("Empty gifs directory");
            return false;
        }

        return true;
    }

    void begin() {
        decoder.setScreenClearCallback(screenClearCallback);
        decoder.setUpdateScreenCallback(updateScreenCallback);
        decoder.setDrawPixelCallback(drawPixelCallback);

        decoder.setFileSeekCallback(fileSeekCallback);
        decoder.setFilePositionCallback(filePositionCallback);
        decoder.setFileReadCallback(fileReadCallback);
        decoder.setFileReadBlockCallback(fileReadBlockCallback);
        decoder.setFileSizeCallback(fileSizeCallback);

        Serial.println("Starting GIFHandler");

        matrix.addLayer(&backgroundLayer);
        matrix.addLayer(&scrollingLayer);
        matrix.setBrightness(255);
        matrix.begin();

        backgroundLayer.fillScreen({0, 0, 0});
        backgroundLayer.swapBuffers();

        if (!checkSDCard()) {
            while (1);  // halt execution if SD card or GIFs directory is not available
        }
    }

    bool openFile(int index) {
        if (openGifFilenameByIndex(GIF_DIRECTORY, index) < 0) {
            return true;  // Indicate that the next GIF should be loaded
        }

        if (decoder.startDecoding() < 0) {
            return true;  // Indicate that the next GIF should be loaded
        }

        return false;  // Indicate that the current GIF should play
    }

    bool playGIF() {
        return decoder.decodeFrame() < 0;
    }

    void performTimedTasks() {
        static unsigned long displayStartTimeMillis;
        static bool nextGIF = true;
        static int index = 0;

        unsigned long now = millis();

        if (shouldPlayNextGIF(now)) {
            nextGIF = openFile(index);
            if (nextGIF) {
                index = (index + 1) % num_files;
            } else {
                displayStartTimeMillis = now;
            }
        }

        if (nextGIF || playGIF()) {
            nextGIF = true;
            index = (index + 1) % num_files;
        }
    }

    bool shouldPlayNextGIF(unsigned long now) {
        return (now - displayStartTimeMillis) > (DISPLAY_TIME_SECONDS * 1000) || decoder.getCycleNumber() > NUMBER_FULL_CYCLES;
    }
}

#endif // GIF_HANDLER_H