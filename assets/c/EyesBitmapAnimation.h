#ifndef BITMAP_ANIMATION_H
#define BITMAP_ANIMATION_H

#include <SmartMatrix.h>
#include "Config.h"
#include "EyesBitmap.h" // Include your bitmap file

// Define the matrix width and height
#define MATRIX_WIDTH 64
#define MATRIX_HEIGHT 64

namespace EyesBitmapAnimation {
    const rgb24 kBackgroundColor = {0, 0, 0}; // Background color (black)
    const rgb24 kForegroundColor = {0, 0, 255}; // Foreground color (blue)
    const int kFaceSpacing = 2; // Space between the two faces
    const int animationInterval = 1500; // Animation interval in milliseconds (1.5 seconds)
    unsigned long lastUpdate = 0; // Last update timestamp
    int currentMood = 0; // Current mood index
    int currentPos = 0; // Current position index

    void begin() {
        // Add the background layer to the matrix and initialize it
        matrix.addLayer(&backgroundLayer);
        matrix.begin();
        matrix.setBrightness(128);
    }

    // Function to draw a scaled bitmap at a given position
    void drawBitmap(const uint8_t* bitmap, int x_offset, int y_offset, int original_width, int original_height, int scaled_width, int scaled_height) {
        for (int y = 0; y < scaled_height; y++) {
            for (int x = 0; x < scaled_width; x++) {
                int src_x = x * original_width / scaled_width;
                int src_y = y * original_height / scaled_height;
                bool pixelOn = pgm_read_byte(bitmap + src_y * (original_width / 8) + src_x / 8) & (1 << (7 - (src_x % 8)));
                rgb24 color = pixelOn ? kForegroundColor : kBackgroundColor;
                backgroundLayer.drawPixel(x + x_offset, y + y_offset, color);
            }
        }
    }

    // Function to display both eyes with specified mood and position
    void displayEyes(int mood, int pos, int original_width, int original_height, int scaled_width, int scaled_height) {
        backgroundLayer.fillScreen(kBackgroundColor); // Clear the screen

        int left_eye_x = (MATRIX_WIDTH - 2 * scaled_width - kFaceSpacing) / 2; // Calculate X position for the left eye
        int left_eye_y = (MATRIX_HEIGHT - scaled_height) / 2; // Center vertically
        int right_eye_x = left_eye_x + scaled_width + kFaceSpacing; // Calculate X position for the right eye
        int right_eye_y = left_eye_y; // Align vertically with left eye

        drawBitmap(peyes[mood][pos][0], left_eye_x, left_eye_y, original_width, original_height, scaled_width, scaled_height);
        drawBitmap(peyes[mood][pos][1], right_eye_x, right_eye_y, original_width, original_height, scaled_width, scaled_height);

        backgroundLayer.swapBuffers(); // Update the display
    }

    // Function to update the animation
    void updateAnimation() {
        unsigned long currentTime = millis();
        if (currentTime - lastUpdate >= animationInterval) {
            lastUpdate = currentTime;
            currentPos++;
            if (currentPos > 2) {
                currentPos = 0;
                currentMood++;
                if (currentMood > 5) {
                    currentMood = 0;
                }
            }
            displayEyes(currentMood, currentPos, 32, 32, 16, 16); // Display the next eye set
        }
    }

    // Function to perform timed tasks
    void performTimedTasks() {
        updateAnimation();
        delay(100); // Small delay to prevent high CPU usage
    }

    // Function to display a bitmap (placeholder for additional functionality)
    void DisplayBitmap() {
        // drawBitmap(eye0, 32, 32); // Uncomment and adjust width and height as necessary
    }
}

#endif // BITMAP_ANIMATION_H