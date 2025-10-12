#include "ClockAnimation.h"

namespace ClockAnimation {
    // Digit patterns for a 3x5 font
    const uint8_t digits[10][5] = {
        {0x1F, 0x11, 0x1F}, // 0
        {0x00, 0x1F, 0x00}, // 1
        {0x1D, 0x15, 0x17}, // 2
        {0x15, 0x15, 0x1F}, // 3
        {0x07, 0x04, 0x1F}, // 4
        {0x17, 0x15, 0x1D}, // 5
        {0x1F, 0x15, 0x1D}, // 6
        {0x01, 0x01, 0x1F}, // 7
        {0x1F, 0x15, 0x1F}, // 8
        {0x17, 0x15, 0x1F}  // 9
    };

    void setup() {
        // Initialize SmartMatrix background layer
        LedMatrixHandler::backgroundLayer.setBrightness(100);
        LedMatrixHandler::backgroundLayer.fillScreen(kBackgroundColor);
        LedMatrixHandler::backgroundLayer.swapBuffers();
    }

    void update() {
        // Get current time
        int hours = hour();
        int minutes = minute();
        int seconds = second();

        // Draw the clock
        drawClock(hours, minutes, seconds);
    }

    void drawClock(int hours, int minutes, int seconds) {
        clearScreen();

        // Draw hours
        drawDigit(2, 2, hours / 10, kForegroundColor);
        drawDigit(8, 2, hours % 10, kForegroundColor);

        // Draw minutes
        drawDigit(18, 2, minutes / 10, kForegroundColor);
        drawDigit(24, 2, minutes % 10, kForegroundColor);

        // Draw seconds
        drawDigit(34, 2, seconds / 10, kForegroundColor);
        drawDigit(40, 2, seconds % 10, kForegroundColor);

        LedMatrixHandler::backgroundLayer.swapBuffers();
    }

    void drawDigit(int x, int y, int digit, rgb24 color) {
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 5; j++) {
                if (digits[digit][i] & (1 << j)) {
                    LedMatrixHandler::backgroundLayer.drawPixel(x + i, y + j, color);
                }
            }
        }
    }

    void clearScreen() {
        LedMatrixHandler::backgroundLayer.fillScreen(kBackgroundColor);
    }
}