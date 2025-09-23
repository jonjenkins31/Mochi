#ifndef SPRITE_HANDLER_H
#define SPRITE_HANDLER_H

#include <Arduino.h>
#include <SmartMatrix.h>

namespace SpriteHandler {
    const int SPRITE_WIDTH = 64;
    const int SPRITE_HEIGHT = 64;
    const int SPRITES_PER_ROW = 4;

    uint16_t* spriteSheet;  // This should point to your sprite sheet data

    uint16_t applyColorFilter(uint16_t color, uint16_t targetColor, uint16_t newColor) {
        if (color == targetColor) {
            return newColor;
        }
        return color;
    }

    void drawSprite(int x, int y, int spriteIndex, bool useFilter = false, uint16_t targetColor = 0, uint16_t newColor = 0) {
        int frameX = (spriteIndex % SPRITES_PER_ROW) * SPRITE_WIDTH;
        int frameY = (spriteIndex / SPRITES_PER_ROW) * SPRITE_HEIGHT;

        for (int i = 0; i < SPRITE_WIDTH; i++) {
            for (int j = 0; j < SPRITE_HEIGHT; j++) {
                uint16_t color = spriteSheet[(frameY + j) * (SPRITE_WIDTH * SPRITES_PER_ROW) + (frameX + i)];
                if (useFilter && targetColor != 0) {
                    color = applyColorFilter(color, targetColor, newColor);
                }
                backgroundLayer.drawPixel(x + i, y + j, color);
            }
        }
        backgroundLayer.swapBuffers();
    }

    void playAnimation(int x, int y, int startFrame, int endFrame, int delayMs, bool useFilter = false, uint16_t targetColor = 0, uint16_t newColor = 0) {
        for (int frame = startFrame; frame <= endFrame; frame++) {
            drawSprite(x, y, frame, useFilter, targetColor, newColor);
            delay(delayMs);
        }
    }

    void begin(uint16_t* sheet) {
        spriteSheet = sheet;
        Serial.println("Starting SpriteHandler");
        matrix.addLayer(&backgroundLayer);
        matrix.setBrightness(255);
        matrix.begin();
        backgroundLayer.fillScreen({0, 0, 0});
        backgroundLayer.swapBuffers();
    }
}

#endif // SPRITE_HANDLER_H