#ifndef LEDMATRIXHANDLER_H
#define LEDMATRIXHANDLER_H


#include <Arduino.h>
#include <SD.h>
#include <SPI.h>



#define USE_ADAFRUIT_GFX_LAYERS


// uncomment one line to select your MatrixHardware configuration - configuration header needs to be included before <SmartMatrix.h>
//#include <MatrixHardware_Teensy3_ShieldV4.h>        // SmartLED Shield for Teensy 3 (V4)
#include <MatrixHardware_Teensy4_ShieldV5.h>        // SmartLED Shield for Teensy 4 (V5)
//#include <MatrixHardware_Teensy3_ShieldV1toV3.h>    // SmartMatrix Shield for Teensy 3 V1-V3
//#include <MatrixHardware_Teensy4_ShieldV4Adapter.h> // Teensy 4 Adapter attached to SmartLED Shield for Teensy 3 (V4)
//#include <MatrixHardware_ESP32_V0.h>                // This file contains multiple ESP32 hardware configurations, edit the file to define GPIOPINOUT (or add #define GPIOPINOUT with a hardcoded number before this #include)
//#include "MatrixHardware_Custom.h"                  // Copy an existing MatrixHardware file to your Sketch directory, rename, customize, and you can include it like this
#include <SmartMatrix.h>


// SmartMatrix setup parameters
#define COLOR_DEPTH 24                  // Choose the color depth used for storing pixels in the layers: 24 or 48 (24 is good for most sketches - If the sketch uses type `rgb24` directly, COLOR_DEPTH must be 24)
const uint16_t kMatrixWidth = 64;       // Set to the width of your display, must be a multiple of 8
const uint16_t kMatrixHeight = 64;      // Set to the height of your display
const uint8_t kRefreshDepth = 36;       // Tradeoff of color quality vs refresh rate, max brightness, and RAM usage.  36 is typically good, drop down to 24 if you need to.  On Teensy, multiples of 3, up to 48: 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48.  On ESP32: 24, 36, 48
const uint8_t kDmaBufferRows = 4;       // known working: 2-4, use 2 to save RAM, more to keep from dropping frames and automatically lowering refresh rate.  (This isn't used on ESP32, leave as default)
const uint8_t kPanelType = SM_PANELTYPE_HUB75_64ROW_MOD32SCAN;   // Choose the configuration that matches your panels.  See more details in MatrixCommonHub75.h and the docs: https://github.com/pixelmatix/SmartMatrix/wiki
const uint32_t kMatrixOptions = (SM_HUB75_OPTIONS_NONE);        // see docs for options: https://github.com/pixelmatix/SmartMatrix/wiki
const uint8_t kBackgroundLayerOptions = (SM_BACKGROUND_OPTIONS_NONE);
const uint8_t kScrollingLayerOptions = (SM_SCROLLING_OPTIONS_NONE);
const uint8_t kIndexedLayerOptions = (SM_INDEXED_OPTIONS_NONE);

// Generate buffer layers
SMARTMATRIX_ALLOCATE_BUFFERS(matrix, kMatrixWidth, kMatrixHeight, kRefreshDepth, kDmaBufferRows, kPanelType, kMatrixOptions);
SMARTMATRIX_ALLOCATE_BACKGROUND_LAYER(backgroundLayer, kMatrixWidth, kMatrixHeight, COLOR_DEPTH, kBackgroundLayerOptions);
SMARTMATRIX_ALLOCATE_SCROLLING_LAYER(scrollingLayer, kMatrixWidth, kMatrixHeight, COLOR_DEPTH, kScrollingLayerOptions);
SMARTMATRIX_ALLOCATE_INDEXED_LAYER(indexedLayer, kMatrixWidth, kMatrixHeight, COLOR_DEPTH, kIndexedLayerOptions);





#define SD_CS BUILTIN_SDCARD  // Define the SD card chip select pin


#include "AdafruitGFX.h"
#include "Bitmaps.h"
#include "animated_gifs.h"
#include "FeatureDemo.h"
#include "SerialHandler.h"
#include "TimerAnimation.h"
#include "EyesAnimation.h"
#include "EyesBitmapAnimation.h"
#include "GIF_Handler.h"





uint16_t spriteSheetData[] = {
    // Insert your sprite sheet pixel data here
    // For example, you can use a tool to convert your image to a 1D array of pixel data
};





namespace LedMatrixHandler {

  // enable this to see the intermediate drawing steps, otherwise screen will only be updated at the end of each test (this slows the tests down considerably)
  const bool swapAfterEveryDraw = false;

  void begin() {
        Serial.println("Led Matrix Handler Initialization Started");

        // Initialize the SD card
        if (!SD.begin(SD_CS)) {
            Serial.println("SD card initialization failed!");
            while (1);
        }
        Serial.println("SD card initialized.");

        // Initialize SmartMatrix
        matrix.addLayer(&backgroundLayer);
        matrix.begin();
        matrix.setBrightness(255);
        backgroundLayer.fillScreen({0, 0, 0});
        backgroundLayer.swapBuffers();

        GIFHandler::setupDecoder();






    //AdafruitGFX::begin();
    //Bitmaps::begin();
    //EyesBitmapAnimation::begin();
    //AnimatedGifs::begin();
    //BMPHandler::begin(spriteSheetData);

    //AnimatedGifs::begin();
    //TimerAnimation::startCountdown(5);
    Serial.println("Led Matrix Handler Initialization Completed");

  }
 
  bool limitFrameRate = true; // Set this to false to disable frame rate limiting

  void handleCommand() {
      static unsigned long lastUpdate = 0;
      static unsigned long frameCount = 0;
      static unsigned long frameRateLastUpdate = 0;
      static const unsigned long targetFrameRate = 60; // Desired frames per second
      static const unsigned long frameInterval = 1000 / targetFrameRate; // Interval per frame in milliseconds
      unsigned long currentTime = millis();

      // Variables to track average execution time
      static unsigned long totalExecutionTime = 0;
      static unsigned long executionCount = 0;

      // Check if it's time to move to the next frame
      if (!limitFrameRate || (currentTime - lastUpdate >= frameInterval)) {
          lastUpdate = currentTime; // Update the last recorded time

          unsigned long startTime = micros(); // Start time measurement

          // Perform your regular LED Matrix handling tasks here
          //EyesAnimation::performTimedTasks();
          //Bitmaps::performTimedTasks();
          //AdafruitGFX::performTimedTasks();
          AnimatedGifs::performTimedTasks();
          //BMPHandler::playAnimation(0, 0, 0, 3, 200);  // Play frames 0 to 3 with 200ms delay

          unsigned long endTime = micros(); // End time measurement
          unsigned long executionTime = endTime - startTime;
          totalExecutionTime += executionTime;
          executionCount++;

          // Frame rate calculation
          frameCount++;
          if (currentTime - frameRateLastUpdate >= 1000) {
              // Calculate average execution time
              unsigned long averageExecutionTime = totalExecutionTime / executionCount;

              // Print frame rate and average execution time
              SerialHandler::printMessage("LED Matrix Frame rate: " + String(frameCount) + " FPS", SerialHandler::FRAMERATE);
              SerialHandler::printMessage("Average Execution Time: " + String(averageExecutionTime) + " µs", SerialHandler::FRAMERATE);

              // Reset counters
              frameCount = 0;
              frameRateLastUpdate = currentTime;
              totalExecutionTime = 0;
              executionCount = 0;
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

      // Variables to track average execution time
      static unsigned long totalExecutionTime = 0;
      static unsigned long executionCount = 0;

      // Check if it's time to move to the next frame
      if (!limitFrameRate || (currentTime - lastUpdate >= frameInterval)) {
          lastUpdate = currentTime; // Update the last recorded time

          unsigned long startTime = micros(); // Start time measurement

          // Perform your regular LED Matrix handling tasks here
          //TimerAnimation::performTimedTasks();

          unsigned long endTime = micros(); // End time measurement
          unsigned long executionTime = endTime - startTime;
          totalExecutionTime += executionTime;
          executionCount++;

          // Frame rate calculation
          frameCount++;
          if (currentTime - frameRateLastUpdate >= 1000) {
              // Calculate average execution time
              unsigned long averageExecutionTime = totalExecutionTime / executionCount;

              // Print frame rate and average execution time
              SerialHandler::printMessage("LED Matrix Frame rate: " + String(frameCount) + " FPS", SerialHandler::FRAMERATE);
              SerialHandler::printMessage("Average Execution Time: " + String(averageExecutionTime) + " µs", SerialHandler::FRAMERATE);

              // Reset counters
              frameCount = 0;
              frameRateLastUpdate = currentTime;
              totalExecutionTime = 0;
              executionCount = 0;
          }
      }
  }



    void displaySprite(const char* spriteFile, int matrixX, int matrixY, int spriteStartX, int spriteStartY) {
        // Open and display the sprite
        if (Bitmaps::openBMPFile(spriteFile)) {
            Bitmaps::drawBMPFrame(matrixX, matrixY, spriteStartX, spriteStartY);
            Bitmaps::closeBMPFile();
        } else {
            Serial.println("Failed to open sprite file!");
        }
    }

    void displayGIF(const char* gifFile) {
        // Open and play the GIF
        if (GIFHandler::openGIFFile(gifFile)) {
            GIFHandler::playGIF();
            GIFHandler::closeGIFFile();
        } else {
            Serial.println("Failed to open GIF file!");
        }
    }


  // Function to perform timed tasks in sequence
  void performTimedTasks() {
    // Static variable to store the last time the function was updated
    static unsigned long previousMillis = 0;
    // Static variable to track the current stage of the task sequence
    static int stage = 0;
    // Define the intervals for each stage in milliseconds
    const unsigned long stageIntervals[] = {7000, 7000, 7000, 7000, 7000};
    // Number of stages
    const int numStages = 7; // Number of stages
    // Get the current time
    unsigned long currentMillis = millis();
    // Static variable to check if it's the first run
    static int lastStage = -1; // Store the last stage to detect stage change


    int x, y;



    const rgb24 kBackgroundColor = {0, 0, 0};
    const rgb24 kForegroundColor = {255, 255, 255};


    // Check if the task is completed
    if (currentMillis - previousMillis >= 7000) {
      Serial.println("Time lapse: " + String(currentMillis - previousMillis) + " milliseconds");
      // Move to the next stage
      stage++;
      // Reset stage if it exceeds the number of stages
      if (stage >= numStages) {
        stage = 0;
      }
    }

    // Change of state
    if (stage != lastStage) { // Check if the stage has changed
      // Update the last recorded time
      previousMillis = currentMillis;
      lastStage = stage; // Update the last stage
      Serial.println("Stage changed to: " + String(stage) );
    }

    // Perform actions based on the current stage every cycle
    switch (stage) {
      case 0:
      displaySprite("bmps/random_emotes.bmp", 0, 0, 838, 324);
        break;
      case 1:
      displaySprite("bmps/random_emotes.bmp", 0, 0, 968, 196);
        break;
      case 2:
          Bitmaps::animations(0); // Scale to 64x64

      //displayGIF("gifs/ezgif.com-resize-5.gif");
        break;
      case 3:
          Bitmaps::animations(1); // Scale to 64x64

      //displayGIF("gifs/ezgif.com-resize-6.gif");
        break;
      case 4:
                Bitmaps::animations(2); // Scale to 64x64

      //displayGIF("gifs/ChasmDaltynRun.gif");
        break;




      case 5:

          Bitmaps::animations(0); // Scale to 64x64
          break;

      case 6:
          Bitmaps::animations(1); // Scale to 64x64

          break;

      case 7:
          Bitmaps::animations(2); // Scale to 64x64

          break;




    }
  }













} // namespace LedMatrixHandler



#endif