#ifndef GIF_HANDLER_H
#define GIF_HANDLER_H

#include <Arduino.h>
#include <GifDecoder.h>
#include <SD.h>
#include <SPI.h>
#include <SmartMatrix.h>


namespace GIFHandler {
    GifDecoder<kMatrixWidth, kMatrixHeight, 12> decoder;
    File gifFile;

    void screenClearCallback() {
        backgroundLayer.fillScreen({0, 0, 0});
    }

    void updateScreenCallback() {
        backgroundLayer.swapBuffers();
    }

    void drawPixelCallback(int16_t x, int16_t y, uint8_t red, uint8_t green, uint8_t blue) {
        backgroundLayer.drawPixel(x, y, {red, green, blue});
    }

    bool fileSeekCallback(unsigned long position) {
        return gifFile.seek(position);
    }

    unsigned long filePositionCallback() {
        return gifFile.position();
    }

    int fileReadCallback() {
        return gifFile.read();
    }

    int fileReadBlockCallback(void *buffer, int numberOfBytes) {
        return gifFile.read((uint8_t*)buffer, numberOfBytes);
    }

    unsigned long fileSizeCallback() {
        return gifFile.size();
    }



    // Open GIF file from SD card
    bool openGIFFile(const char *filename) {
        gifFile = SD.open(filename);
        if (!gifFile) {
            Serial.println("Failed to open GIF file!");
            return false;
        }
        return true;
    }

    // Close GIF file
    void closeGIFFile() {
        if (gifFile) {
            gifFile.close();
        }
    }

    // Set up the GIF decoder
    void setupDecoder() {
        // Set GIF decoder callbacks
        decoder.setScreenClearCallback(screenClearCallback);
        decoder.setUpdateScreenCallback(updateScreenCallback);
        decoder.setDrawPixelCallback(drawPixelCallback);
        decoder.setFileSeekCallback(fileSeekCallback);
        decoder.setFilePositionCallback(filePositionCallback);
        decoder.setFileReadCallback(fileReadCallback);
        decoder.setFileReadBlockCallback(fileReadBlockCallback);
        decoder.setFileSizeCallback(fileSizeCallback);
    }


    // Play the GIF
    void playGIF() {
        if (decoder.startDecoding() < 0) {
            Serial.println("Failed to start decoding!");
            return;
        }

        while (decoder.decodeFrame() == 0) {
            delay(decoder.getFrameDelay_ms());  // Use the correct method to get frame delay
        }
    }
}

#endif // GIF_HANDLER_H