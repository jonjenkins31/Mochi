#ifndef ADAFRUIT_GFX_H
#define ADAFRUIT_GFX_H

#include <Arduino.h>
#include "LedMatrixHandler.h"
#include "Config.h"

namespace AdafruitGFX {

  // enable this to see the intermediate drawing steps, otherwise screen will only be updated at the end of each test (this slows the tests down considerably)
  const bool swapAfterEveryDraw = false;

  unsigned long testFillScreen() {
    unsigned long start = micros();
    backgroundLayer.fillScreen(BLACK);
    backgroundLayer.fillScreen(RED);
    backgroundLayer.fillScreen(GREEN);
    backgroundLayer.fillScreen(BLUE);
    backgroundLayer.fillScreen(BLACK);
    return micros() - start;
  }

  unsigned long testText() {
    backgroundLayer.fillScreen(BLACK);
    unsigned long start = micros();
    backgroundLayer.setCursor(0, 0);
    backgroundLayer.setTextColor(WHITE);  backgroundLayer.setTextSize(1);
    backgroundLayer.println("Hello World!");
    backgroundLayer.setTextColor(YELLOW); backgroundLayer.setTextSize(2);
    backgroundLayer.println(1234.56);
    backgroundLayer.setTextColor(RED);    backgroundLayer.setTextSize(3);
  //  backgroundLayer.println(0xDEADBEEF, HEX);
  //  backgroundLayer.println();
    backgroundLayer.setTextColor(GREEN);
    backgroundLayer.setTextSize(5);
    backgroundLayer.println("Groop");
    backgroundLayer.setTextSize(2);
    backgroundLayer.println("I implore thee,");
    backgroundLayer.setTextSize(1);
    backgroundLayer.println("my foonting turlingdromes.");
    backgroundLayer.println("And hooptiously drangle me");
    backgroundLayer.println("with crinkly bindlewurdles,");
    backgroundLayer.println("Or I will rend thee");
    backgroundLayer.println("in the gobberwarts");
    backgroundLayer.println("with my blurglecruncheon,");
    backgroundLayer.println("see if I don't!");
    return micros() - start;
  }

  unsigned long testLines(uint16_t color) {
    unsigned long start, t;
    int           x1, y1, x2, y2,
                  w = backgroundLayer.width(),
                  h = backgroundLayer.height();

    backgroundLayer.fillScreen(BLACK);

    x1 = y1 = 0;
    y2    = h - 1;
    start = micros();
    for(x2=0; x2<w; x2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    x2    = w - 1;
    for(y2=0; y2<h; y2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    t     = micros() - start; // fillScreen doesn't count against timing
    backgroundLayer.swapBuffers();

    backgroundLayer.fillScreen(BLACK);

    x1    = w - 1;
    y1    = 0;
    y2    = h - 1;
    start = micros();
    for(x2=0; x2<w; x2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    x2    = 0;
    for(y2=0; y2<h; y2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    t    += micros() - start;
    backgroundLayer.swapBuffers();

    backgroundLayer.fillScreen(BLACK);

    x1    = 0;
    y1    = h - 1;
    y2    = 0;
    start = micros();
    for(x2=0; x2<w; x2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    x2    = w - 1;
    for(y2=0; y2<h; y2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    t    += micros() - start;
    backgroundLayer.swapBuffers();

    backgroundLayer.fillScreen(BLACK);

    x1    = w - 1;
    y1    = h - 1;
    y2    = 0;
    start = micros();
    for(x2=0; x2<w; x2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    x2    = 0;
    for(y2=0; y2<h; y2+=6) {
      backgroundLayer.drawLine(x1, y1, x2, y2, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    t    += micros() - start;
    backgroundLayer.swapBuffers();

    return t;
  }
  unsigned long testFastLines(uint16_t color1, uint16_t color2) {
    unsigned long start;
    int           x, y, w = backgroundLayer.width(), h = backgroundLayer.height();

    backgroundLayer.fillScreen(BLACK);
    start = micros();
    for(y=0; y<h; y+=5) {
      backgroundLayer.drawFastHLine(0, y, w, color1);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }
    for(x=0; x<w; x+=5) {
      backgroundLayer.drawFastVLine(x, 0, h, color2);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }

    return micros() - start;
  }

  unsigned long testRects(uint16_t color) {
    unsigned long start;
    int           n, i, i2,
                  cx = backgroundLayer.width()  / 2,
                  cy = backgroundLayer.height() / 2;

    backgroundLayer.fillScreen(BLACK);
    n     = min(backgroundLayer.width(), backgroundLayer.height());
    start = micros();
    for(i=2; i<n; i+=6) {
      i2 = i / 2;
      backgroundLayer.drawRect(cx-i2, cy-i2, i, i, color);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }

    return micros() - start;
  }

  unsigned long testFilledRects(uint16_t color1, uint16_t color2) {
    unsigned long start, t = 0;
    int           n, i, i2,
                  cx = backgroundLayer.width()  / 2 - 1,
                  cy = backgroundLayer.height() / 2 - 1;

    backgroundLayer.fillScreen(BLACK);
    n = min(backgroundLayer.width(), backgroundLayer.height());
    for(i=n; i>0; i-=6) {
      i2    = i / 2;
      start = micros();
      backgroundLayer.fillRect(cx-i2, cy-i2, i, i, color1);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
      t    += micros() - start;
      // Outlines are not included in timing results
      backgroundLayer.drawRect(cx-i2, cy-i2, i, i, color2);
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }

    return t;
  }

  unsigned long testFilledCircles(uint8_t radius, uint16_t color) {
    unsigned long start;
    int x, y, w = backgroundLayer.width(), h = backgroundLayer.height(), r2 = radius * 2;

    backgroundLayer.fillScreen(BLACK);
    start = micros();
    for(x=radius; x<w; x+=r2) {
      for(y=radius; y<h; y+=r2) {
        backgroundLayer.fillCircle(x, y, radius, color);
        if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
      }
    }

    return micros() - start;
  }

  unsigned long testCircles(uint8_t radius, uint16_t color) {
    unsigned long start;
    int           x, y, r2 = radius * 2,
                  w = backgroundLayer.width()  + radius,
                  h = backgroundLayer.height() + radius;

    // Screen is not cleared for this one -- this is
    // intentional and does not affect the reported time.
    start = micros();
    for(x=0; x<w; x+=r2) {
      for(y=0; y<h; y+=r2) {
        backgroundLayer.drawCircle(x, y, radius, color);
        if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
      }
    }

    return micros() - start;
  }

  unsigned long testTriangles() {
    unsigned long start;
    int           n, i, cx = backgroundLayer.width()  / 2 - 1,
                        cy = backgroundLayer.height() / 2 - 1;

    backgroundLayer.fillScreen(BLACK);
    n     = min(cx, cy);
    start = micros();
    for(i=0; i<n; i+=5) {
      backgroundLayer.drawTriangle(
        cx    , cy - i, // peak
        cx - i, cy + i, // bottom left
        cx + i, cy + i, // bottom right
        backgroundLayer.color565(0, 0, i));
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }

    return micros() - start;
  }

  unsigned long testFilledTriangles() {
    unsigned long start, t = 0;
    int           i, cx = backgroundLayer.width()  / 2 - 1,
                    cy = backgroundLayer.height() / 2 - 1;

    backgroundLayer.fillScreen(BLACK);
    start = micros();
    for(i=min(cx,cy); i>10; i-=5) {
      start = micros();
      backgroundLayer.fillTriangle(cx, cy - i, cx - i, cy + i, cx + i, cy + i,
        backgroundLayer.color565(0, i, i));
      t += micros() - start;
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
      backgroundLayer.drawTriangle(cx, cy - i, cx - i, cy + i, cx + i, cy + i,
        backgroundLayer.color565(i, i, 0));
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }

    return t;
  }

  unsigned long testRoundRects() {
    unsigned long start;
    int           w, i, i2,
                  cx = backgroundLayer.width()  / 2 - 1,
                  cy = backgroundLayer.height() / 2 - 1;

    backgroundLayer.fillScreen(BLACK);
    w     = min(backgroundLayer.width(), backgroundLayer.height());
    start = micros();
    for(i=0; i<w; i+=6) {
      i2 = i / 2;
      backgroundLayer.drawRoundRect(cx-i2, cy-i2, i, i, i/8, backgroundLayer.color565(i, 0, 0));
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }

    return micros() - start;
  }

  unsigned long testFilledRoundRects() {
    unsigned long start;
    int           i, i2,
                  cx = backgroundLayer.width()  / 2 - 1,
                  cy = backgroundLayer.height() / 2 - 1;

    backgroundLayer.fillScreen(BLACK);
    start = micros();
    for(i=min(backgroundLayer.width(), backgroundLayer.height()); i>20; i-=6) {
      i2 = i / 2;
      backgroundLayer.fillRoundRect(cx-i2, cy-i2, i, i, i/8, backgroundLayer.color565(0, i, 0));
      if(swapAfterEveryDraw) backgroundLayer.swapBuffers();
    }

    return micros() - start;
  }

void rotateScreen() {
  static uint8_t rotation = 0; // Tracks the current rotation value (0 to 3)

  // Perform the rotation
  backgroundLayer.setRotation(rotation);
  testText();
  backgroundLayer.swapBuffers();

  // Move to the next rotation value
  rotation++;
  if (rotation > 3) {
    rotation = 0; // Reset rotation value after completing all rotations
  }
}



  void begin() {
    matrix.addLayer(&backgroundLayer);
    matrix.begin();
    matrix.setBrightness(128);
  }

  void performTimedTasks() {
    static unsigned long previousMillis = 0; // stores the last time the function was updated
    static unsigned int stage = 0; // tracks the current stage of the task sequence
    // Define the intervals for each stage in milliseconds
    const unsigned long intervals[] = {500, 3000, 500, 500, 500, 500, 500, 500, 500, 500, 500,500, 5000}; // durations for each stage
    // Get the current time
    unsigned long currentMillis = millis();

    // Check if it's time to move to the next stage
    if (currentMillis - previousMillis >= intervals[stage]) {
      previousMillis = currentMillis; // Update the last recorded time
      stage++; // Move to the next stage
      if (stage >= sizeof(intervals) / sizeof(intervals[0])) {
        stage = 0; // Reset stage
      }
    }


 // Perform actions based on the current stage
  switch (stage) {
    case 0:
      // SerialHandler::printInlineMessage(F("Screen fill              "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testFillScreen()), SerialHandler::TASK);
      testFillScreen();
      delay(100); // Small delay to ensure drawing operations complete
      backgroundLayer.swapBuffers();
      break;

    case 1:
      // SerialHandler::printInlineMessage(F("Text                     "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testText()), SerialHandler::TASK);
      testText();
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 2:
      // SerialHandler::printInlineMessage(F("Lines                    "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testLines(CYAN)), SerialHandler::TASK);
      testLines(CYAN);
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 3:
      // SerialHandler::printInlineMessage(F("Horiz/Vert Lines         "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testFastLines(RED, BLUE)), SerialHandler::TASK);
      testFastLines(RED, BLUE);
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 4:
      // SerialHandler::printInlineMessage(F("Rectangles (outline)     "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testRects(GREEN)), SerialHandler::TASK);
      testRects(GREEN);
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 5:
      // SerialHandler::printInlineMessage(F("Rectangles (filled)      "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testFilledRects(YELLOW, MAGENTA)), SerialHandler::TASK);
      testFilledRects(YELLOW, MAGENTA);
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 6:
      // SerialHandler::printInlineMessage(F("Circles (filled)         "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testFilledCircles(10, MAGENTA)), SerialHandler::TASK);
      testFilledCircles(10, MAGENTA);
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 7:
      // SerialHandler::printInlineMessage(F("Circles (outline)        "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testCircles(10, WHITE)), SerialHandler::TASK);
      testCircles(10, WHITE);
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 8:
      // SerialHandler::printInlineMessage(F("Triangles (outline)      "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testTriangles()), SerialHandler::TASK);
      testTriangles();
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 9:
      // SerialHandler::printInlineMessage(F("Triangles (filled)       "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testFilledTriangles()), SerialHandler::TASK);
      testFilledTriangles();
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 10:
      // SerialHandler::printInlineMessage(F("Rounded rects (outline)  "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testRoundRects()), SerialHandler::TASK);
      testRoundRects();
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 11:
      // SerialHandler::printInlineMessage(F("Rounded rects (filled)   "), SerialHandler::TASK);
      // SerialHandler::printMessage(String(testFilledRoundRects()), SerialHandler::TASK);
      testFilledRoundRects();
      delay(100);
      backgroundLayer.swapBuffers();
      break;

    case 12: // New stage for screen rotation
      rotateScreen();
      delay(50); // Delay between rotations
      break;

    
  }

  }



} // namespace LedMatrixHandler










#endif // ADAFRUIT_GFX_H