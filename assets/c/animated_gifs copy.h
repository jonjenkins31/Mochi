#ifndef ANIMATED_GIFS_H
#define ANIMATED_GIFS_H

#include <Arduino.h>
#include "LedMatrixHandler.h"
#include <SmartMatrix.h>
#include <SD.h>
#include <GifDecoder.h>
#include "Filename_Functions.h"




#define DISPLAY_TIME_SECONDS 10
#define NUMBER_FULL_CYCLES   100

#define USE_SMARTMATRIX         1
#define ENABLE_SCROLLING        1




// range 0-255
const int defaultBrightness = 255;

const rgb24 COLOR_BLACK = {
    0, 0, 0 };

GifDecoder<kMatrixWidth, kMatrixHeight, 12> decoder;

// Chip select for SD card
#if defined(ESP32)
    #define SD_CS 5
#elif defined (ARDUINO)
    #define SD_CS BUILTIN_SDCARD
    //#define SD_CS 15
#endif

#if defined(ESP32)
    // ESP32 SD Library can't handle a trailing slash in the directory name
    #define GIF_DIRECTORY "/gifs"
#else
    // Teensy SD Library requires a trailing slash in the directory name
    #define GIF_DIRECTORY "/gifs/"
#endif

int num_files;



namespace AnimatedGifs {

    
  void screenClearCallback(void) {
  #if (USE_SMARTMATRIX == 1)
    backgroundLayer.fillScreen({0,0,0});
  #endif
  }

  void updateScreenCallback(void) {
  #if (USE_SMARTMATRIX == 1)
    backgroundLayer.swapBuffers();
  #endif
  }

  void drawPixelCallback(int16_t x, int16_t y, uint8_t red, uint8_t green, uint8_t blue) {
  #if (USE_SMARTMATRIX == 1)
      backgroundLayer.drawPixel(x, y, {red, green, blue});
  #endif
  }

  bool checkSDCard() {
      if (initFileSystem(SD_CS) < 0) {
  #if (ENABLE_SCROLLING == 1)
          scrollingLayer.start("No SD card", -1);
  #endif
          Serial.println("No SD card");
          return false;
      }

      num_files = enumerateGIFFiles(GIF_DIRECTORY, true);

      if (num_files < 0) {
  #if (ENABLE_SCROLLING == 1)
          scrollingLayer.start("No gifs directory", -1);
  #endif
          Serial.println("No gifs directory");
          return false;
      }

      if (!num_files) {
  #if (ENABLE_SCROLLING == 1)
          scrollingLayer.start("Empty gifs directory", -1);
  #endif
          Serial.println("Empty gifs directory");
          return false;
      }

      return true;
  }

  
  // Setup method runs once, when the sketch starts
  void begin() {
      decoder.setScreenClearCallback(screenClearCallback);
      decoder.setUpdateScreenCallback(updateScreenCallback);
      decoder.setDrawPixelCallback(drawPixelCallback);

      decoder.setFileSeekCallback(fileSeekCallback);
      decoder.setFilePositionCallback(filePositionCallback);
      decoder.setFileReadCallback(fileReadCallback);
      decoder.setFileReadBlockCallback(fileReadBlockCallback);
      decoder.setFileSizeCallback(fileSizeCallback);

      Serial.println("Starting AnimatedGIFs Sketch");

      #if (USE_SMARTMATRIX == 1)
          // Initialize matrix
          matrix.addLayer(&backgroundLayer);
      #if (ENABLE_SCROLLING == 1)
          matrix.addLayer(&scrollingLayer);
      #endif

          matrix.setBrightness(defaultBrightness);

          // for large panels, may want to set the refresh rate lower to leave more CPU time to decoding GIFs (needed if GIFs are playing back slowly)
          //matrix.setRefreshRate(90);

      #if !defined(ESP32)
          matrix.begin();
      #else
          // for large panels on ESP32, may want to set the max percentage time dedicated to updating the refresh frames lower, to leave more CPU time to decoding GIFs (needed if GIFs are playing back slowly)
          //matrix.setMaxCalculationCpuPercentage(50);

          // alternatively, for large panels on ESP32, may want to set the calculation refresh rate divider lower to leave more CPU time to decoding GIFs (needed if GIFs are playing back slowly) - this has the same effect as matrix.setMaxCalculationCpuPercentage() but is set with a different parameter
          //matrix.setCalcRefreshRateDivider(4);

          // The ESP32 SD Card library is going to want to malloc about 28000 bytes of DMA-capable RAM, make sure at least that much is left free
          matrix.begin(28000);
      #endif

          // Clear screen
          backgroundLayer.fillScreen(COLOR_BLACK);
          backgroundLayer.swapBuffers();
      #endif

      if (!checkSDCard()) {
          while (1);  // halt execution if SD card or GIFs directory is not available
      }
  }




    void performTimedTasks() {

      static unsigned long displayStartTime_millis;
      static int nextGIF = 1;     // we haven't loaded a GIF yet on first pass through, make sure we do that

      unsigned long now = millis();

      static int index = 0;

  #if 1
      // default behavior is to play the gif for DISPLAY_TIME_SECONDS or for NUMBER_FULL_CYCLES, whichever comes first
      if((now - displayStartTime_millis) > (DISPLAY_TIME_SECONDS * 1000) || decoder.getCycleNumber() > NUMBER_FULL_CYCLES)
          nextGIF = 1;
  #else
      // alt behavior is to play the gif until both DISPLAY_TIME_SECONDS and NUMBER_FULL_CYCLES have passed
      if((now - displayStartTime_millis) > (DISPLAY_TIME_SECONDS * 1000) && decoder.getCycleNumber() > NUMBER_FULL_CYCLES)
          nextGIF = 1;
  #endif

      if(nextGIF)
      {
          nextGIF = 0;

          if (openGifFilenameByIndex(GIF_DIRECTORY, index) >= 0) {
              // Can clear screen for new animation here, but this might cause flicker with short animations
              // matrix.fillScreen(COLOR_BLACK);
              // matrix.swapBuffers();

              // start decoding, skipping to the next GIF if there's an error
              if(decoder.startDecoding() < 0) {
                  nextGIF = 1;
                  return;
              }

              // Calculate time in the future to terminate animation
              displayStartTime_millis = now;
          }

          // get the index for the next pass through
          if (++index >= num_files) {
              index = 0;
          }

      }

      if(decoder.decodeFrame() < 0) {
          // There's an error with this GIF, go to the next one
          nextGIF = 1;
      }
      }

}

#endif // ANIMATED_GIFS_H