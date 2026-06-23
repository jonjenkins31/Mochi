// Config.h
#ifndef CONFIG_H
#define CONFIG_H

// Enum for system states
enum SystemState {
    BOOTING,
    NORMAL,
    ABNORMAL
};

// Global variables
extern unsigned long bootTimeout; // Timeout for booting in milliseconds



// Color definitions for NeoPixelHandler
#define NEO_BLUE   0x000000FF
#define NEO_RED    0x00FF0000
#define NEO_GREEN  0x0000FF00
#define NEO_YELLOW 0x00FFD000
#define NEO_WHITE  0xAA000000

// Color definitions for LedMatrixHandler
// Assign human-readable names to some common 16-bit color values:
#define BLACK   0x0000
#define BLUE    0x001F
#define RED     0xF800
#define GREEN   0x07E0
#define CYAN    0x07FF
#define MAGENTA 0xF81F
#define YELLOW  0xFFE0
#define WHITE   0xFFFF




#endif