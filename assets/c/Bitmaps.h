#ifndef BITMAPS_H
#define BITMAPS_H

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include <SmartMatrix.h>
#include "LedMatrixHandler.h"
#include "bitmaps/gimpbitmap.h"

// pixelmatix.c is a bitmap exported from GIMP without modification
#include "bitmaps/pixelmatix.c"

// colorwheel.c has been modified to use the gimp32x32bitmap struct
#include "bitmaps/colorwheel.c"

// chrome16 is a 16x16 pixel bitmap, exported from GIMP without modification
#include "bitmaps/chrome16.c"

namespace Bitmaps {

    extern bool swapAfterEveryDraw;
    extern bool limitFrameRate;

    const rgb24 kBackgroundColor = {0, 0, 0};
    const rgb24 kForegroundColor = {255, 255, 255};

    void begin() {
        matrix.addLayer(&backgroundLayer);
        matrix.begin();
        matrix.setBrightness(128);
    }

    void drawBitmap(int x_offset, int y_offset, const gimp32x32bitmap* bitmap, int original_width, int original_height, int scaled_width, int scaled_height) {
        for (int y = 0; y < scaled_height; y++) {
            for (int x = 0; x < scaled_width; x++) {
                int src_x = x * original_width / scaled_width;
                int src_y = y * original_height / scaled_height;
                SM_RGB pixel = { 
                    bitmap->pixel_data[(src_y * original_width + src_x) * 3 + 0],
                    bitmap->pixel_data[(src_y * original_width + src_x) * 3 + 1],
                    bitmap->pixel_data[(src_y * original_width + src_x) * 3 + 2] 
                };
                if (COLOR_DEPTH == 48) {
                    pixel.red = pixel.red << 8;
                    pixel.green = pixel.green << 8;
                    pixel.blue = pixel.blue << 8;
                }
                backgroundLayer.drawPixel(x + x_offset, y + y_offset, pixel);
            }
        }
    }

    void animations(int state) {
    int x, y;
    const rgb24 kBackgroundColor = {0, 0, 0};
    const rgb24 kForegroundColor = {255, 255, 255};

      switch (state) {
          case 0:
              backgroundLayer.fillScreen(kBackgroundColor);
              x = (kMatrixWidth / 2) - (64 / 2); // Scaled size
              y = (kMatrixHeight / 2) - (64 / 2); // Scaled size
              drawBitmap(x, y, (const gimp32x32bitmap*)&pixelmatixlogo, 32, 32, 64, 64); // Scale to 64x64
              backgroundLayer.swapBuffers();
              break;

          case 1:
              backgroundLayer.fillScreen(kBackgroundColor);
              x = (kMatrixWidth / 2) - (48 / 2); // Scaled size
              y = (kMatrixHeight / 2) - (48 / 2); // Scaled size
              drawBitmap(x, y, &colorwheel, 32, 32, 48, 48); // Scale to 48x48
              backgroundLayer.swapBuffers();
              break;

          case 2:
              backgroundLayer.fillScreen(kBackgroundColor);
              x = (kMatrixWidth / 2) - (32 / 2); // Scaled size
              y = (kMatrixHeight / 2) - (32 / 2); // Scaled size
              drawBitmap(x, y, (const gimp32x32bitmap*)&chrome16, 16, 16, 32, 32); // Scale to 32x32
              backgroundLayer.swapBuffers();
              break;
      }
    }




    File bmpFile;

    // Open BMP file from SD card
    bool openBMPFile(const char *filename) {
        bmpFile = SD.open(filename);
        if (!bmpFile) {
            Serial.println("Failed to open BMP file!");
            return false;
        }
        return true;
    }

    // Close BMP file
    void closeBMPFile() {
        if (bmpFile) {
            bmpFile.close();
        }
    }

    // Read BMP header to get image width, height, and pixel data offset
    bool readBMPHeader(int &width, int &height, int &offset) {
        if (!bmpFile) return false;

        bmpFile.seek(10);
        offset = bmpFile.read() | (bmpFile.read() << 8) | (bmpFile.read() << 16) | (bmpFile.read() << 24);

        bmpFile.seek(18);
        width = bmpFile.read() | (bmpFile.read() << 8) | (bmpFile.read() << 16) | (bmpFile.read() << 24);

        bmpFile.seek(22);
        height = bmpFile.read() | (bmpFile.read() << 8) | (bmpFile.read() << 16) | (bmpFile.read() << 24);

        return true;
    }

    // Draw BMP frame starting from a specific location in the BMP file to a specific location on the LED matrix
    void drawBMPFrame(int matrixX, int matrixY, int startX, int startY) {
        if (!bmpFile) return;

        int bmpWidth, bmpHeight, bmpOffset;
        if (!readBMPHeader(bmpWidth, bmpHeight, bmpOffset)) return;

        // Print image size and window coordinates for debugging
        Serial.print("Image size: ");
        Serial.print(bmpWidth);
        Serial.print("x");
        Serial.println(bmpHeight);
        Serial.print("Window size: ");
        Serial.print(kMatrixWidth);
        Serial.print("x");
        Serial.println(kMatrixHeight);
        Serial.print("Window coordinates: (");
        Serial.print(startX);
        Serial.print(", ");
        Serial.print(startY);
        Serial.println(")");

        // Each row is padded to a multiple of 4 bytes
        int rowSize = (3 * bmpWidth + 3) & ~3;

        // Calculate the offset to the starting pixel in the BMP file, considering the bottom-left corner
        int offset = bmpOffset + ((bmpHeight - startY - 1) * rowSize) + startX * 3;

        for (int j = 0; j < kMatrixHeight; j++) {
            // Adjust for top-down display on the LED matrix
            int rowOffset = offset - j * rowSize;  
            bmpFile.seek(rowOffset);

            for (int i = 0; i < kMatrixWidth; i++) {
                // Read pixel data (BMP stores as BGR, need to convert to RGB)
                uint8_t b = bmpFile.read();
                uint8_t g = bmpFile.read();
                uint8_t r = bmpFile.read();

                // Draw pixel on the matrix
                backgroundLayer.drawPixel(matrixX + i, matrixY + j, {r, g, b});
            }
        }
        // Update the display
        backgroundLayer.swapBuffers();
    }

















}

#endif // BITMAPS_H