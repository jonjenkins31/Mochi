#include <Arduino.h>
#include "Config.h"
#include "SerialHandler.h"
#include "NeoPixelHandler.h"
#include "LedMatrixHandler.h"
//#include "AnimatedGifs.ino"
//#include "SimpleAnimations.ino"
//#include "ComplexAnimations.ino"
//#include "GameAnimations.ino"
#include "MicrophoneHandler.h"

SystemState currentState = BOOTING;
unsigned long bootStartTime;

void setup() {
  SerialHandler::begin();
  // Start the booting state
  currentState = BOOTING;
  bootStartTime = millis();

  // Initialize other handlers
  NeoPixelHandler::begin();
  LedMatrixHandler::begin();
  //MicrophoneHandler::setup();

 // setupAnimatedGifs(); // Initialize GIF animations
  //setupSimpleAnimations(); // Initialize simple animations
  //setupComplexAnimations(); // Initialize complex animations
  //setupGameAnimations(); // Initialize game animations

  // Enable or disable different types of messages
  SerialHandler::enableErrorMessages = true;   // Set to false to disable error messages
  SerialHandler::enableStatusMessages = true;  // Set to false to disable status messages
  SerialHandler::enableTaskMessages = true;    // Set to false to disable task messages
  SerialHandler::enableFrameRateMessages = true; // Set to false to disable frame rate messages
  Serial.println("Initialization completed");

}

void loop() {
    String command = SerialHandler::readCommand();


    switch (currentState) {
        case BOOTING:
            NeoPixelHandler::bootingCommand();
            LedMatrixHandler::bootingCommand();
            if (SerialHandler::isSerialEstablished() || millis() - bootStartTime > bootTimeout) {
                currentState = NORMAL;
                SerialHandler::printMessage("Transition to NORMAL state", SerialHandler::STATUS);
            }
            Serial.println("booting");
            break;
        case NORMAL:
            // Main operation
           // String command = SerialHandler::readCommand();
            /*
            if (command.length() > 0) {
              if (command.startsWith("Pixel1 ") || command.startsWith("Pixel2 ")) {
                NeoPixelHandler::handleCommand(command);
              } else {
                Serial.println("Unknown command: " + command);
              }
            }
            */
            NeoPixelHandler::handleCommand();
            LedMatrixHandler::  performTimedTasks();
            //MicrophoneHandler::testMicrophones();

            // Add your main logic here
            break;
        case ABNORMAL:
            // Handle error condition
            SerialHandler::printMessage("System in ABNORMAL state", SerialHandler::ERROR);
            // Add your error handling logic here
            break;
    }

}