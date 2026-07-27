#ifndef LED_MATRIX_HANDLER_H
#define LED_MATRIX_HANDLER_H

#include <Arduino.h>
#include <SmartMatrix.h>

namespace LEDMatrixHandler {
    const int MATRIX_WIDTH = 64;
    const int MATRIX_HEIGHT = 64;
    const int COLOR_DEPTH = 24;

    // SmartMatrix setup
    typedef rgb24 color_t;
    const uint8_t kPanelType = SMARTMATRIX_HUB75_64ROW_MOD32SCAN;
    SmartMatrix3<kPanelType, MATRIX_WIDTH, MATRIX_HEIGHT, COLOR_DEPTH, SMARTMATRIX_OPTIONS_NONE> matrix;
    SMLayerBackground<rgb24> backgroundLayer(matrix);
    SMLayerScrolling<rgb24> scrollingLayer(matrix);

    void begin() {
        Serial.println("Starting LEDMatrixHandler");
        matrix.addLayer(&backgroundLayer);
        matrix.addLayer(&scrollingLayer);
        matrix.setBrightness(255);
        matrix.begin();
        clear();
    }

    void clear() {
        backgroundLayer.fillScreen({0, 0, 0});
        backgroundLayer.swapBuffers();
    }

    void drawText(int x, int y, const char* text, color_t color) {
        backgroundLayer.drawString(x, y, color, text);
        backgroundLayer.swapBuffers();
    }

    void scrollText(const char* text, color_t color, int speed) {
        scrollingLayer.setColor(color);
        scrollingLayer.setMode(wrapForward);
        scrollingLayer.setSpeed(speed);
        scrollingLayer.start(text);
    }

    void drawPixel(int x, int y, color_t color) {
        backgroundLayer.drawPixel(x, y, color);
        backgroundLayer.swapBuffers();
    }

    void drawLine(int x1, int y1, int x2, int y2, color_t color) {
        backgroundLayer.drawLine(x1, y1, x2, y2, color);
        backgroundLayer.swapBuffers();
    }

    void drawRectangle(int x, int y, int width, int height, color_t color, bool filled) {
        if (filled) {
            backgroundLayer.fillRectangle(x, y, x + width - 1, y + height - 1, color);
        } else {
            backgroundLayer.drawRectangle(x, y, x + width - 1, y + height - 1, color);
        }
        backgroundLayer.swapBuffers();
    }

    void drawCircle(int x, int y, int radius, color_t color, bool filled) {
        if (filled) {
            backgroundLayer.fillCircle(x, y, radius, color);
        } else {
            backgroundLayer.drawCircle(x, y, radius, color);
        }
        backgroundLayer.swapBuffers();
    }

    void rotateDisplay(int angle) {
        matrix.setRotation(angle);
        backgroundLayer.swapBuffers();
    }

    color_t color(uint8_t red, uint8_t green, uint8_t blue) {
        return { red, green, blue };
    }
}

#endif // LED_MATRIX_HANDLER_H






void setup() {
    LEDMatrixHandler::begin();
    
    // Clear the screen
    LEDMatrixHandler::clear();
    
    // Draw some text
    LEDMatrixHandler::drawText(0, 0, "Hello!", LEDMatrixHandler::color(255, 255, 255));
    
    // Scroll some text
    LEDMatrixHandler::scrollText("Scrolling Text", LEDMatrixHandler::color(0, 255, 0), 50);
    
    // Draw shapes
    LEDMatrixHandler::drawRectangle(10, 10, 30, 30, LEDMatrixHandler::color(255, 0, 0), true);
    LEDMatrixHandler::drawCircle(50, 50, 10, LEDMatrixHandler::color(0, 0, 255), false);
    
    // Rotate the display
    LEDMatrixHandler::rotateDisplay(1); // Rotate 90 degrees
}



