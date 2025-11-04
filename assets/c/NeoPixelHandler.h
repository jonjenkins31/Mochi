#ifndef NEOPIXEL_HANDLER_H
#define NEOPIXEL_HANDLER_H

#include "SerialHandler.h" 

//Required Library
#include <WS2812Serial.h>

// Define the number of LEDs in each NeoPixel strip
#define NUM_LEDS_LTNeoPixel 24
#define NUM_LEDS_RTNeoPixel 24
int LTNeoPixelPixelOrder[NUM_LEDS_LTNeoPixel] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}; 
int RTNeoPixelPixelOrder[NUM_LEDS_RTNeoPixel] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}; 

// Define the data pins for each strip
#define DATA_PIN_LTNeoPixel 24
#define DATA_PIN_RTNeoPixel 29
// Usable pins:
//   Teensy LC:   1, 4, 5, 24
//   Teensy 3.2:  1, 5, 8, 10, 31   (overclock to 120 MHz for pin 8)
//   Teensy 3.5:  1, 5, 8, 10, 26, 32, 33, 48
//   Teensy 3.6:  1, 5, 8, 10, 26, 32, 33
//   Teensy 4.0:  1, 8, 14, 17, 20, 24, 29, 39
//   Teensy 4.1:  1, 8, 14, 17, 20, 24, 29, 35, 47, 53

byte drawingMemory1[NUM_LEDS_LTNeoPixel*4];         //  4 bytes per LED for RGBW
DMAMEM byte displayMemory1[NUM_LEDS_LTNeoPixel*16]; // 16 bytes per LED for RGBW

byte drawingMemory2[NUM_LEDS_RTNeoPixel*4];         //  4 bytes per LED for RGBW
DMAMEM byte displayMemory2[NUM_LEDS_RTNeoPixel*16]; // 16 bytes per LED for RGBW

WS2812Serial LTNeoPixel(NUM_LEDS_LTNeoPixel, displayMemory1, drawingMemory1, DATA_PIN_LTNeoPixel, WS2812_GRBW);
WS2812Serial RTNeoPixel(NUM_LEDS_RTNeoPixel, displayMemory2, drawingMemory2, DATA_PIN_RTNeoPixel, WS2812_GRBW);



// Timing variables
unsigned long previousMillis = 0;
const long interval = 20; // Interval for the animation in milliseconds


namespace NeoPixelHandler {

  void begin() {
    LTNeoPixel.begin();
    LTNeoPixel.setBrightness(200); // 0=off, 255=brightest
    RTNeoPixel.begin();
    RTNeoPixel.setBrightness(200); // 0=off, 255=brightest
  }


  // Input a value 0 to 255 to get a color value.
  // The colors are a transition r - g - b - back to r.
  uint32_t Wheel(byte WheelPos) {
    WheelPos = 255 - WheelPos;
    if (WheelPos < 85) {
      return LTNeoPixel.Color(255 - WheelPos * 3, WheelPos * 3, 0);
    }
    if (WheelPos < 170) {
      WheelPos -= 85;
      return LTNeoPixel.Color(0, 255 - WheelPos * 3, WheelPos * 3);
    }
    WheelPos -= 170;
    return LTNeoPixel.Color(WheelPos * 3, 0, 255 - WheelPos * 3);
  }

  //--------------------------- non blocking versions of neopixel animation -

  void colorWipe1(uint32_t color, unsigned long wait) {
    static int pixelIndex1 = 0;
    static unsigned long previousMillis1 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis1 >= wait) {
      previousMillis1 = currentMillis;

      if (pixelIndex1 < LTNeoPixel.numPixels()) {
        LTNeoPixel.setPixel(pixelIndex1, color); // Set pixel's color (in RAM)
        LTNeoPixel.show();                       // Update strip to match
        pixelIndex1++;
      } else {
        pixelIndex1 = 0; // Restart from pixel 0
      }
    }
  }

  void colorWipe2(uint32_t color, unsigned long wait) {
    static int pixelIndex2 = 0;
    static unsigned long previousMillis2 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis2 >= wait) {
      previousMillis2 = currentMillis;

      if (pixelIndex2 < RTNeoPixel.numPixels()) {
        RTNeoPixel.setPixel(pixelIndex2, color); // Set pixel's color (in RAM)
        RTNeoPixel.show();                       // Update strip to match
        pixelIndex2++;
      } else {
        pixelIndex2 = 0; // Restart from pixel 0
      }
    }
  }

  void ColorWipeOrder1(uint32_t color, unsigned long wait, int* pixelOrder) {
    static int pixelIndex1 = 0;
    static unsigned long previousMillis1 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis1 >= wait) {
      previousMillis1 = currentMillis;

      if (pixelIndex1 < NUM_LEDS_LTNeoPixel) {
        LTNeoPixel.setPixel(pixelOrder[pixelIndex1], color);
        LTNeoPixel.show(); // Update strip to match
        pixelIndex1++;
      } else {
        pixelIndex1 = 0;
      }
    }
  }

  void ColorWipeOrder2(uint32_t color, unsigned long wait, int* pixelOrder) {
    static int pixelIndex2 = 0;
    static unsigned long previousMillis2 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis2 >= wait) {
      previousMillis2 = currentMillis;

      if (pixelIndex2 < NUM_LEDS_RTNeoPixel) {
        RTNeoPixel.setPixel(pixelOrder[pixelIndex2], color);
        RTNeoPixel.show(); // Update strip to match
        pixelIndex2++;
      } else {
        pixelIndex2 = 0;
      }
    }
  }

  void theaterChase1(uint32_t color, unsigned long wait, unsigned int groupSize, unsigned int numChases) {
    static unsigned int chase1 = 0;
    static unsigned int pos1 = 0;
    static unsigned long previousMillis1 = 0;

    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis1 >= wait) {
      previousMillis1 = currentMillis;

      LTNeoPixel.clear();  // turn off all LEDs
      for (unsigned int i = pos1; i < LTNeoPixel.numPixels(); i += groupSize) {
        LTNeoPixel.setPixel(i, color);  // turn on the current group
      }
      LTNeoPixel.show();

      pos1++;
      if (pos1 >= groupSize) {
        pos1 = 0;
        chase1++;
        if (chase1 >= numChases) {
          chase1 = 0; // Reset for the next call
        }
      }
    }
  }

  void theaterChase2(uint32_t color, unsigned long wait, unsigned int groupSize, unsigned int numChases) {
    static unsigned int chase2 = 0;
    static unsigned int pos2 = 0;
    static unsigned long previousMillis2 = 0;

    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis2 >= wait) {
      previousMillis2 = currentMillis;

      RTNeoPixel.clear();  // turn off all LEDs
      for (unsigned int i = pos2; i < RTNeoPixel.numPixels(); i += groupSize) {
        RTNeoPixel.setPixel(i, color);  // turn on the current group
      }
      RTNeoPixel.show();

      pos2++;
      if (pos2 >= groupSize) {
        pos2 = 0;
        chase2++;
        if (chase2 >= numChases) {
          chase2 = 0; // Reset for the next call
        }
      }
    }
  }

  void theaterChaseRainbow1(unsigned long wait, unsigned int groupSize, unsigned int numChases) {
    static unsigned int chase1 = 0;
    static unsigned int pos1 = 0;
    static unsigned long previousMillis1 = 0;
    static byte colorIndex1 = 0;

    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis1 >= wait) {
      previousMillis1 = currentMillis;

      LTNeoPixel.clear();  // turn off all LEDs
      for (unsigned int i = pos1; i < LTNeoPixel.numPixels(); i += groupSize) {
        uint32_t color = Wheel((colorIndex1 + i) & 255);
        LTNeoPixel.setPixel(i, color);  // turn on the current group
      }
      LTNeoPixel.show();

      pos1++;
      if (pos1 >= groupSize) {
        pos1 = 0;
        chase1++;
        colorIndex1 += 256 / numChases;  // Change color for the next cycle
        if (chase1 >= numChases) {
          chase1 = 0; // Reset for the next call
          colorIndex1 = 0; // Reset color index
        }
      }
    }
  }

  void theaterChaseRainbow2(unsigned long wait, unsigned int groupSize, unsigned int numChases) {
    static unsigned int chase2 = 0;
    static unsigned int pos2 = 0;
    static unsigned long previousMillis2 = 0;
    static byte colorIndex2 = 0;

    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis2 >= wait) {
      previousMillis2 = currentMillis;

      RTNeoPixel.clear();  // turn off all LEDs
      for (unsigned int i = pos2; i < RTNeoPixel.numPixels(); i += groupSize) {
        uint32_t color = Wheel((colorIndex2 + i) & 255);
        RTNeoPixel.setPixel(i, color);  // turn on the current group
      }
      RTNeoPixel.show();

      pos2++;
      if (pos2 >= groupSize) {
        pos2 = 0;
        chase2++;
        colorIndex2 += 256 / numChases;  // Change color for the next cycle
        if (chase2 >= numChases) {
          chase2 = 0; // Reset for the next call
          colorIndex2 = 0; // Reset color index
        }
      }
    }
  }

  void rainbow1(uint8_t wait) {
    static uint16_t j1 = 0;
    static unsigned long previousMillis1 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis1 >= wait) {
      previousMillis1 = currentMillis;

      for (uint16_t i = 0; i < LTNeoPixel.numPixels(); i++) {
        LTNeoPixel.setPixel(i, Wheel((i + j1) & 255));
      }
      LTNeoPixel.show();
      j1++;
      if (j1 >= 256) {
        j1 = 0; // Reset for the next call
      }
    }
  }

  void rainbow2(uint8_t wait) {
    static uint16_t j2 = 0;
    static unsigned long previousMillis2 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis2 >= wait) {
      previousMillis2 = currentMillis;

      for (uint16_t i = 0; i < RTNeoPixel.numPixels(); i++) {
        RTNeoPixel.setPixel(i, Wheel((i + j2) & 255));
      }
      RTNeoPixel.show();
      j2++;
      if (j2 >= 256) {
        j2 = 0; // Reset for the next call
      }
    }
  }

  void rainbowCycle1(uint8_t wait) {
    static uint16_t j1 = 0;
    static unsigned long previousMillis1 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis1 >= wait) {
      previousMillis1 = currentMillis;

      for (uint16_t i = 0; i < LTNeoPixel.numPixels(); i++) {
        LTNeoPixel.setPixel(i, Wheel(((i * 256 / LTNeoPixel.numPixels()) + j1) & 255));
      }
      LTNeoPixel.show();

      j1++;
      if (j1 >= 256 * 5) {
        j1 = 0; // Reset for the next call
      }
    }
  }

  void rainbowCycle2(uint8_t wait) {
    static uint16_t j2 = 0;
    static unsigned long previousMillis2 = 0;
    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis2 >= wait) {
      previousMillis2 = currentMillis;

      for (uint16_t i = 0; i < RTNeoPixel.numPixels(); i++) {
        RTNeoPixel.setPixel(i, Wheel(((i * 256 / RTNeoPixel.numPixels()) + j2) & 255));
      }
      RTNeoPixel.show();

      j2++;
      if (j2 >= 256 * 5) {
        j2 = 0; // Reset for the next call
      }
    }
  }


  void setSingleLED1(uint16_t LEDnum, uint32_t c) {
    LTNeoPixel.setPixelColor(LEDnum, c);
    LTNeoPixel.show();
  }

  void setSingleLED2(uint16_t LEDnum, uint32_t c) {
    RTNeoPixel.setPixelColor(LEDnum, c);
    RTNeoPixel.show();
  }

  void blank1(unsigned long wait) {
    LTNeoPixel.clear();
    LTNeoPixel.show();
    delay(wait);
  }

  void blank2(unsigned long wait) {
    RTNeoPixel.clear();
    RTNeoPixel.show();
    delay(wait);
  }

  void rainbowCycleWithWhiteOverlay1( unsigned long whiteSpeed, int whiteLength, unsigned long colorSpeed) {
    static uint16_t colorIndex1 = 0;
    static uint16_t whiteIndex1 = 0;
    static unsigned long previousColorMillis1 = 0;
    static unsigned long previousWhiteMillis1 = 0;

    unsigned long currentMillis = millis();

    // Calculate the new color position
    if (currentMillis - previousColorMillis1 >= colorSpeed) {
      previousColorMillis1 = currentMillis;
      colorIndex1++;
      if (colorIndex1 >= 256 * 5) {
        colorIndex1 = 0; // Reset for the next call
      }
    }

    // Calculate the new white position
    if (currentMillis - previousWhiteMillis1 >= whiteSpeed) {
      previousWhiteMillis1 = currentMillis;
      whiteIndex1++;
      if (whiteIndex1 >= LTNeoPixel.numPixels()) {
        whiteIndex1 = 0; // Reset for the next call
      }
    }

    // Update the strip with both color and white sections
    for (uint16_t i = 0; i < LTNeoPixel.numPixels(); i++) {
      // Calculate the color
      uint32_t color = Wheel(((i * 256 / LTNeoPixel.numPixels()) + colorIndex1) & 255);
      LTNeoPixel.setPixel(i, color);

      // Determine if this pixel should be white
      int relativePos = (i - whiteIndex1 + LTNeoPixel.numPixels()) % LTNeoPixel.numPixels();
      if (relativePos < whiteLength) {
        LTNeoPixel.setPixel(i, LTNeoPixel.Color(0, 0, 0, 255)); // Set white
      }
    }

    LTNeoPixel.show();
  }

  void rainbowCycleWithWhiteOverlay2(unsigned long whiteSpeed, int whiteLength, unsigned long colorSpeed) {
    static uint16_t colorIndex = 0;
    static uint16_t whiteIndex = 0;
    static unsigned long previousColorMillis = 0;
    static unsigned long previousWhiteMillis = 0;

    unsigned long currentMillis = millis();

    // Calculate the new color position
    if (currentMillis - previousColorMillis >= colorSpeed) {
      previousColorMillis = currentMillis;
      colorIndex++;
      if (colorIndex >= 256 * 5) {
        colorIndex = 0; // Reset for the next call
      }
    }

    // Calculate the new white position
    if (currentMillis - previousWhiteMillis >= whiteSpeed) {
      previousWhiteMillis = currentMillis;
      whiteIndex++;
      if (whiteIndex >= RTNeoPixel.numPixels()) {
        whiteIndex = 0; // Reset for the next call
      }
    }

    // Update the strip with both color and white sections
    for (uint16_t i = 0; i < RTNeoPixel.numPixels(); i++) {
      // Calculate the color
      uint32_t color = Wheel(((i * 256 / RTNeoPixel.numPixels()) + colorIndex) & 255);
      RTNeoPixel.setPixel(i, color);

      // Determine if this pixel should be white
      int relativePos = (i - whiteIndex + RTNeoPixel.numPixels()) % RTNeoPixel.numPixels();
      if (relativePos < whiteLength) {
        RTNeoPixel.setPixel(i, RTNeoPixel.Color(0, 0, 0, 255)); // Set white
      }
    }

    RTNeoPixel.show();
  }



  void pulseWhite1(uint8_t wait) {
    static int j1 = 0;
    static bool increasing1 = true;
    static unsigned long previousMillis1 = 0;

    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis1 >= wait) {
      previousMillis1 = currentMillis;

      uint32_t whiteColor = LTNeoPixel.Color(0, 0, 0, j1);

      if (increasing1) {
        for (int i = 0; i < LTNeoPixel.numPixels(); i++) {
          LTNeoPixel.setPixel(i, whiteColor);
        }
        LTNeoPixel.show();
        j1++;
        if (j1 >= 255) {
          increasing1 = false;
        }
      } else {
        for (int i = 0; i < LTNeoPixel.numPixels(); i++) {
          LTNeoPixel.setPixel(i, whiteColor);
        }
        LTNeoPixel.show();
        j1--;
        if (j1 <= 0) {
          increasing1 = true;
        }
      }
    }
  }

  void pulseWhite2(uint8_t wait) {
    static int j2 = 0;
    static bool increasing2 = true;
    static unsigned long previousMillis2 = 0;

    unsigned long currentMillis = millis();

    if (currentMillis - previousMillis2 >= wait) {
      previousMillis2 = currentMillis;

      uint32_t whiteColor = RTNeoPixel.Color(0, 0, 0, j2);

      if (increasing2) {
        for (int i = 0; i < RTNeoPixel.numPixels(); i++) {
          RTNeoPixel.setPixel(i, whiteColor);
        }
        RTNeoPixel.show();
        j2++;
        if (j2 >= 255) {
          increasing2 = false;
        }
      } else {
        for (int i = 0; i < RTNeoPixel.numPixels(); i++) {
          RTNeoPixel.setPixel(i, whiteColor);
        }
        RTNeoPixel.show();
        j2--;
        if (j2 <= 0) {
          increasing2 = true;
        }
      }
    }
  }

  uint32_t dimColor(uint32_t color, uint8_t factor) {
    return LTNeoPixel.Color(
      (color >> 16 & 0xFF) * factor / 255,
      (color >> 8 & 0xFF) * factor / 255,
      (color & 0xFF) * factor / 255,
      (color >> 24 & 0xFF) * factor / 255
    );
  }

  void showPercentageWithSwipe1(uint32_t backgroundColor, uint32_t foregroundColor, unsigned long swipeSpeed, unsigned long delayBetweenSwipes, int percentage) {
    static int stage = 0; // 0 = background, 1 = swipe, 2 = delay
    static int swipeIndex = 0;
    static unsigned long lastUpdateTime = 0;
    static unsigned long delayStartTime = 0;

    int numPixels = LTNeoPixel.numPixels();
    int numForegroundPixels = (numPixels * percentage) / 100;

    unsigned long currentMillis = millis();

    switch (stage) {
      case 0: // Set background color
        for (int i = 0; i < numPixels; i++) {
          LTNeoPixel.setPixel(i, backgroundColor);
        }
        LTNeoPixel.show(); // Show the background

        // Move to the next stage
        stage = 1;
        swipeIndex = 0;
        lastUpdateTime = currentMillis;
        break;

      case 1: // Perform the swipe animation
        if (currentMillis - lastUpdateTime >= swipeSpeed) {
          lastUpdateTime = currentMillis;

          // Apply the foreground percentage color with a swipe effect
          if (swipeIndex < numForegroundPixels) {
            LTNeoPixel.setPixel(swipeIndex, foregroundColor);
            LTNeoPixel.show(); // Update strip with new contents
            swipeIndex++;
          } else {
            // Move to the delay stage
            stage = 2;
            delayStartTime = currentMillis;
          }
        }
        break;

      case 2: // Delay between swipes
        if (currentMillis - delayStartTime >= delayBetweenSwipes) {
          // Reset and move back to the background stage
          stage = 0;
        }
        break;
    }
  }


  void showPercentageWithSwipe2(uint32_t backgroundColor, uint32_t foregroundColor, unsigned long swipeSpeed, unsigned long delayBetweenSwipes, int percentage) {
    static int stage2 = 0; // 0 = background, 1 = swipe, 2 = delay
    static int swipeIndex2 = 0;
    static unsigned long lastUpdateTime2 = 0;
    static unsigned long delayStartTime2 = 0;

    int numPixels2 = RTNeoPixel.numPixels();
    int numForegroundPixels2 = (numPixels2 * percentage) / 100;

    unsigned long currentMillis = millis();

    switch (stage2) {
      case 0: // Set background color
        for (int i = 0; i < numPixels2; i++) {
          RTNeoPixel.setPixel(i, backgroundColor);
        }
        RTNeoPixel.show(); // Show the background

        // Move to the next stage
        stage2 = 1;
        swipeIndex2 = 0;
        lastUpdateTime2 = currentMillis;
        break;

      case 1: // Perform the swipe animation
        if (currentMillis - lastUpdateTime2 >= swipeSpeed) {
          lastUpdateTime2 = currentMillis;

          // Apply the foreground percentage color with a swipe effect
          if (swipeIndex2 < numForegroundPixels2) {
            RTNeoPixel.setPixel(swipeIndex2, foregroundColor);
            RTNeoPixel.show(); // Update strip with new contents
            swipeIndex2++;
          } else {
            // Move to the delay stage
            stage2 = 2;
            delayStartTime2 = currentMillis;
          }
        }
        break;

      case 2: // Delay between swipes
        if (currentMillis - delayStartTime2 >= delayBetweenSwipes) {
          // Reset and move back to the background stage
          stage2 = 0;
        }
        break;
    }
  }



  void performTimedTasks() {
    static unsigned long previousMillis = 0; // stores the last time the function was updated
    static unsigned int stage = 0; // tracks the current stage of the task sequence
    // Define the intervals for each stage in milliseconds
    const unsigned long servointervals[] = {5000, 5000, 5000, 5000, 5000, 5000, 5000, 5000, 5000}; // durations for each stage
    // Get the current time
    unsigned long currentMillis = millis();

    // Check if it's time to move to the next stage
    if (currentMillis - previousMillis >= servointervals[stage]) {
      previousMillis = currentMillis; // Update the last recorded time
      stage++; // Move to the next stage
      if (stage >= sizeof(servointervals) / sizeof(servointervals[0])) {
        stage = 0; // Reset stage
      }
    }

      // Perform actions based on the current stage
    switch (stage) {
      case 0:
        colorWipe1(RED, 50); // Red for LTNeoPixel
        colorWipe2(RED, 50); // Red for RTNeoPixel
        break;
      case 1:
        colorWipe1(GREEN, 50); // Green for LTNeoPixel
        colorWipe2(GREEN, 50); // Green for RTNeoPixel
        break;
      case 2:
        colorWipe1(BLUE, 50); // Blue for LTNeoPixel
        colorWipe2(BLUE, 50); // Blue for RTNeoPixel
        break;
      case 3:
        // Specify the information directly in the function call
      showPercentageWithSwipe1(LTNeoPixel.Color(0, 5, 0), LTNeoPixel.Color(0, 255, 0), 50, 1000, 45); // Example with 75% green foreground
      showPercentageWithSwipe2(LTNeoPixel.Color(0, 5, 0), LTNeoPixel.Color(0, 255, 0), 50, 1000, 45); // Example with 75% green foreground
        break;
      case 4:
        theaterChase1( YELLOW, 100, 3, 5); // Yellow for LTNeoPixel
        theaterChase2(YELLOW, 100, 3, 5); // Yellow for RTNeoPixel
        break;
      case 5:
        rainbow1(10); // Rainbow for LTNeoPixel
        rainbow2( 10); // Rainbow for RTNeoPixel
        break;
      case 6:
        rainbowCycleWithWhiteOverlay1(75, 5, 10);
        rainbowCycleWithWhiteOverlay2(75, 5, 10); // If you want to run both strips together
        break;
      case 7:
        pulseWhite1(5); // Pulse white for LTNeoPixel
        pulseWhite2(5); // Pulse white for RTNeoPixel
        break;
      case 8:
        rainbowCycle1( 3); // Rainbow cycle for LTNeoPixel
        rainbowCycle2(3); // Rainbow cycle for RTNeoPixel
        break;
    }
  }


  bool limitFrameRate = true; // Set this to false to disable frame rate limiting

  void handleCommand() {
    static unsigned long lastUpdate = 0;
    static unsigned long frameCount = 0;
    static unsigned long frameRateLastUpdate = 0;
    static const unsigned long targetFrameRate = 60; // Desired frames per second
    static const unsigned long frameInterval = 1000 / targetFrameRate; // Interval per frame in milliseconds
    unsigned long currentTime = millis();

    // Check if it's time to move to the next frame
    if (!limitFrameRate || (currentTime - lastUpdate >= frameInterval)) {
      lastUpdate = currentTime; // Update the last recorded time

      // Perform your regular NeoPixel handling tasks here
      performTimedTasks();

      // Frame rate calculation
      frameCount++;
      if (currentTime - frameRateLastUpdate >= 1000) {
        SerialHandler::printMessage("NeoPixel Frame rate: " + String(frameCount) + " FPS", SerialHandler::FRAMERATE);
        frameCount = 0;
        frameRateLastUpdate = currentTime;
      }
    }
  }


  void bootingCommand() {
    static unsigned long lastUpdate = 0;
    static unsigned long frameCount = 0;
    static unsigned long frameRateLastUpdate = 0;
    static const unsigned long targetFrameRate = 60; // Desired frames per second
    static const unsigned long frameInterval = 1000 / targetFrameRate; // Interval per frame in milliseconds
    unsigned long currentTime = millis();

    // Check if it's time to move to the next frame
    if (!limitFrameRate || (currentTime - lastUpdate >= frameInterval)) {
      lastUpdate = currentTime; // Update the last recorded time

      // Perform your regular NeoPixel handling tasks here
        pulseWhite1(15); // Pulse white for LTNeoPixel
        pulseWhite2(15); // Pulse white for RTNeoPixel
        
      // Frame rate calculation
      frameCount++;
      if (currentTime - frameRateLastUpdate >= 1000) {
        SerialHandler::printMessage("NeoPixel Frame rate: " + String(frameCount) + " FPS", SerialHandler::FRAMERATE);
        frameCount = 0;
        frameRateLastUpdate = currentTime;
      }
    }
  }
} // namespace NeoPixelHandler

#endif // NEOPIXEL_HANDLER_H