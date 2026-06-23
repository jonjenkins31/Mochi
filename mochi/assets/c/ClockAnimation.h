#ifndef CLOCK_ANIMATION_H
#define CLOCK_ANIMATION_H

#include <SmartMatrix.h>
#include <TimeLib.h>
#include "LedMatrixHandler.h"
#include "Config.h"


namespace ClockAnimation {
    // Constants
    const rgb24 kBackgroundColor = {0, 0, 0};
    const rgb24 kForegroundColor = {255, 255, 255};

    // Initialize the clock animation
    void setup();

    // Update the clock animation
    void update();

    // Draw the clock on the matrix
    void drawClock(int hours, int minutes, int seconds);

    // Helper function to draw a digit
    void drawDigit(int x, int y, int digit, rgb24 color);

    // Helper function to clear the screen
    void clearScreen();
}

#endif // CLOCK_ANIMATION_H