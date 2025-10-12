#ifndef EYES_ANIMATION_H
#define EYES_ANIMATION_H

#include <SmartMatrix.h>
#include "Config.h"

// Define the matrix width and height
#define MATRIX_WIDTH 64
#define MATRIX_HEIGHT 64

namespace EyesAnimation {
    const int kBackgroundColor = BLACK;
    const int kForegroundColor = BLUE;

    // Reference state (PIXELS)
    const int ref_eye_height = 20;      // Absolute height
    const int ref_eye_width = 20;       // Absolute width
    const int ref_space_between_eye = 4;  // *2  
    const int ref_corner_radius = 4; // Reduced corner radius for a more rectangular look

    // Current state of the eyes
    int left_eye_height = ref_eye_height;
    int left_eye_width = ref_eye_width;
    int left_eye_x = (MATRIX_WIDTH / 2) - (ref_eye_width / 2) - ref_space_between_eye; // Adjusted position;
    int left_eye_y =  MATRIX_HEIGHT / 2;
    int right_eye_x = (MATRIX_WIDTH / 2) + (ref_eye_width / 2) + ref_space_between_eye; // Adjusted position
    int right_eye_y =  MATRIX_HEIGHT / 2;
    int right_eye_height = ref_eye_height;
    int right_eye_width = ref_eye_width;

    // Wakeup animation state
    int wakeup_step = 0;
    unsigned long wakeup_last_update = 0;
    const int wakeup_total_steps = 5;
    int wakeup_step_duration = 400; // 2 seconds total / 5 steps
    bool wakeup_in_progress = false;
    

    // Animation state
    int animation_step = 0;
    unsigned long animation_last_update = 0;
    bool animation_in_progress = false;

    // Animation durations
    int look_duration = 500; // Duration for look left or right
    int blink_duration = 300; // Duration for blink

    void begin() {
        // Add the background layer to the matrix
        matrix.addLayer(&backgroundLayer);
        matrix.begin();
        matrix.setBrightness(128);
    }

    void draw_eyes(bool update = true) {
        backgroundLayer.fillScreen(kBackgroundColor);
        int x = int(left_eye_x - left_eye_width / 2);
        int y = int(left_eye_y - left_eye_height / 2);
        backgroundLayer.fillRoundRect(x, y, left_eye_width, left_eye_height, ref_corner_radius, kForegroundColor);
        x = int(right_eye_x - right_eye_width / 2);
        y = int(right_eye_y - right_eye_height / 2);
        backgroundLayer.fillRoundRect(x, y, right_eye_width, right_eye_height, ref_corner_radius, kForegroundColor);
        if (update) {
            backgroundLayer.swapBuffers();
        }
    }

     void wakeup(int animationSpeed = 1000) {
        if (!wakeup_in_progress) {
            wakeup_step = 0;
            wakeup_last_update = millis();
            wakeup_step_duration = animationSpeed / wakeup_total_steps;
            wakeup_in_progress = true;
            animation_in_progress = true;
        }

        unsigned long current_time = millis();
        if (current_time - wakeup_last_update >= wakeup_step_duration) {
            wakeup_last_update = current_time;
            wakeup_step++;
        }

        float progress = static_cast<float>(current_time - wakeup_last_update) / wakeup_step_duration;
        if (progress >= 1.0) {
            progress = 1.0;
        }

        switch (wakeup_step) {
            case 0:
                // Step 1: Blank screen
                backgroundLayer.fillScreen(kBackgroundColor);
                backgroundLayer.swapBuffers();
                break;
            case 1:
                // Step 2: Horizontal line (expand width)
                left_eye_height = 2;
                right_eye_height = 2;
                left_eye_width = static_cast<int>(ref_eye_width * progress);
                right_eye_width = static_cast<int>(ref_eye_width * progress);
                draw_eyes();
                break;
            case 2:
                // Step 3: Horizontal line fully open
                left_eye_height = 2;
                right_eye_height = 2;
                left_eye_width = ref_eye_width;
                right_eye_width = ref_eye_width;
                draw_eyes();
                break;
            case 3:
                // Step 4: Vertical line (expand height)
                left_eye_width = ref_eye_width;
                right_eye_width = ref_eye_width;
                left_eye_height = static_cast<int>(ref_eye_height * progress);
                right_eye_height = static_cast<int>(ref_eye_height * progress);
                draw_eyes();
                break;
            case 4:
                // Step 5: Fully open eyes
                left_eye_height = ref_eye_height;
                right_eye_height = ref_eye_height;
                left_eye_width = ref_eye_width;
                right_eye_width = ref_eye_width;
                draw_eyes();
                break;
            default:
                wakeup_step = -1; // Animation complete
                wakeup_in_progress = false;
                animation_in_progress = false;
                break;
        }
    }

void sleep(int animationSpeed = 1000) {
    static int sleep_step = 0;

    if (!animation_in_progress) {
        sleep_step = 0;
        animation_last_update = millis();
        animation_in_progress = true;
    }

    unsigned long current_time = millis();
    float progress = static_cast<float>(current_time - animation_last_update) / animationSpeed;

    if (progress >= 1.0) {
        progress = 1.0;
        sleep_step++;
        animation_last_update = current_time;
    }

    switch (sleep_step) {
        case 0:
            // Step 1: Fully open eyes
            left_eye_height = ref_eye_height;
            right_eye_height = ref_eye_height;
            left_eye_width = ref_eye_width;
            right_eye_width = ref_eye_width;
            draw_eyes();
            break;
        case 1:
            // Step 2: Vertical line (shrink height)
            left_eye_width = ref_eye_width;
            right_eye_width = ref_eye_width;
            left_eye_height = static_cast<int>(ref_eye_height * (1.0 - progress));
            right_eye_height = static_cast<int>(ref_eye_height * (1.0 - progress));
            draw_eyes();
            break;
        case 2:
            // Step 3: Horizontal line fully open
            left_eye_height = 2;
            right_eye_height = 2;
            left_eye_width = ref_eye_width;
            right_eye_width = ref_eye_width;
            draw_eyes();
            break;
        case 3:
            // Step 4: Horizontal line (shrink width)
            left_eye_height = 2;
            right_eye_height = 2;
            left_eye_width = static_cast<int>(ref_eye_width * (1.0 - progress));
            right_eye_width = static_cast<int>(ref_eye_width * (1.0 - progress));
            draw_eyes();
            break;
        case 4:
            // Step 5: Blank screen
            backgroundLayer.fillScreen(kBackgroundColor);
            backgroundLayer.swapBuffers();
            animation_in_progress = false;
            break;
        default:
            animation_in_progress = false;
            break; // Animation complete
    }
}






    void center_eyes(bool update = true, int duration = 500) {
        if (!animation_in_progress) {
            animation_last_update = millis();
            animation_in_progress = true;
        }

        unsigned long current_time = millis();
        float progress = static_cast<float>(current_time - animation_last_update) / duration;

        if (progress >= 1.0) {
            progress = 1.0;
            animation_in_progress = false;
        }

        left_eye_x = (MATRIX_WIDTH / 2) - (ref_eye_width / 2) - ref_space_between_eye;
        left_eye_y = MATRIX_HEIGHT / 2;
        right_eye_x = (MATRIX_WIDTH / 2) + (ref_eye_width / 2) + ref_space_between_eye;
        right_eye_y = MATRIX_HEIGHT / 2;

        draw_eyes(update);
    }

    void move_right_big_eye(int duration = 500) {
        if (!animation_in_progress) {
            animation_last_update = millis();
            animation_in_progress = true;
        }

        unsigned long current_time = millis();
        float progress = static_cast<float>(current_time - animation_last_update) / duration;

        if (progress >= 1.0) {
            progress = 1.0;
            animation_in_progress = false;
        }

        left_eye_x = 10 + ((MATRIX_WIDTH / 2) - (ref_eye_width / 2) - ref_space_between_eye - 10) * progress;
        right_eye_x = 54 + ((MATRIX_WIDTH / 2) + (ref_eye_width / 2) + ref_space_between_eye - 54) * progress;

        draw_eyes();
    }

    void blink() {
        static int blink_step = 0;

        if (!animation_in_progress) {
            blink_step = 0;
            animation_last_update = millis();
            animation_in_progress = true;
        }

        unsigned long current_time = millis();
        float progress = static_cast<float>(current_time - animation_last_update) / blink_duration;

        if (progress >= 1.0) {
            progress = 1.0;
            blink_step++;
            animation_last_update = current_time;
        }

        switch (blink_step) {
            case 0:
                // Step 1: Close eyes
                left_eye_height = static_cast<int>(ref_eye_height * (1.0 - progress));
                right_eye_height = static_cast<int>(ref_eye_height * (1.0 - progress));
                draw_eyes();
                break;
            case 1:
                // Step 2: Open eyes
                left_eye_height = static_cast<int>(ref_eye_height * progress);
                right_eye_height = static_cast<int>(ref_eye_height * progress);
                draw_eyes();
                if (progress == 1.0) {
                    animation_in_progress = false;
                }
                break;
            default:
                animation_in_progress = false;
                break; // Animation complete
        }
    }

    void look_left() {
        if (!animation_in_progress) {
            animation_last_update = millis();
            animation_in_progress = true;
        }

        unsigned long current_time = millis();
        float progress = static_cast<float>(current_time - animation_last_update) / look_duration;

        if (progress >= 1.0) {
            progress = 1.0;
            animation_in_progress = false;
        }

        left_eye_x = (MATRIX_WIDTH / 2) - (ref_eye_width / 2) - ref_space_between_eye - (10 * progress);
        right_eye_x = (MATRIX_WIDTH / 2) + (ref_eye_width / 2) + ref_space_between_eye - (10 * progress);
        draw_eyes();
    }

    void look_right() {
        if (!animation_in_progress) {
            animation_last_update = millis();
            animation_in_progress = true;
        }

        unsigned long current_time = millis();
        float progress = static_cast<float>(current_time - animation_last_update) / look_duration;

        if (progress >= 1.0) {
            progress = 1.0;
            animation_in_progress = false;
        }

        left_eye_x = (MATRIX_WIDTH / 2) - (ref_eye_width / 2) - ref_space_between_eye + (10 * progress);
        right_eye_x = (MATRIX_WIDTH / 2) + (ref_eye_width / 2) + ref_space_between_eye + (10 * progress);
        draw_eyes();
    }



void happy_eye() {
    static int step = 0;
    static unsigned long last_update = 0;
    static bool in_progress = false;

    if (!in_progress) {
        step = 0;
        last_update = millis();
        in_progress = true;
        animation_in_progress = true;
    }

    unsigned long current_time = millis();
    int interval = 1; // Delay interval

    if (current_time - last_update >= interval) {
        last_update = current_time;

        switch (step) {
            case 0:
                center_eyes(false);
                step++;
                break;
            case 1:
            case 2:
            case 3:
            case 4:
            case 5:
            case 6:
            case 7:
            case 8:
            case 9:
                {
                    int offset = ref_eye_height / 2 - (2 * (step - 1));
                    backgroundLayer.fillTriangle(
                        left_eye_x - left_eye_width / 2 - 1, left_eye_y + offset,
                        left_eye_x + left_eye_width / 2 + 1, left_eye_y + 5 + offset,
                        left_eye_x - left_eye_width / 2 - 1, left_eye_y + left_eye_height + offset,
                        kBackgroundColor);

                    backgroundLayer.fillTriangle(
                        right_eye_x + right_eye_width / 2 + 1, right_eye_y + offset,
                        right_eye_x - right_eye_width / 2 - 1, right_eye_y + 5 + offset,
                        right_eye_x + right_eye_width / 2 + 1, right_eye_y + right_eye_height + offset,
                        kBackgroundColor);

                    backgroundLayer.swapBuffers();
                    step++;
                }
                break;
            case 10:
                // Final step to ensure drawing is complete
                backgroundLayer.swapBuffers();
                last_update = current_time;
                step++;
                break;
            case 11:
                // Delay for 1000ms
                if (current_time - last_update >= 1000) {
                    in_progress = false;
                    animation_in_progress = false;
                }
                break;
        }
    }
}


    void saccade(int direction_x, int direction_y) {
        // quick movement of the eye, no size change. Stay at position after movement, will not move back, call again with opposite direction
        // direction == -1 : move left
        // direction == 1 : move right

        int direction_x_movement_amplitude = 8;
        int direction_y_movement_amplitude = 6;
        int blink_amplitude = 8;

        for (int i = 0; i < 1; i++) {
            left_eye_x += direction_x_movement_amplitude * direction_x;
            right_eye_x += direction_x_movement_amplitude * direction_x;
            left_eye_y += direction_y_movement_amplitude * direction_y;
            right_eye_y += direction_y_movement_amplitude * direction_y;

            right_eye_height -= blink_amplitude;
            left_eye_height -= blink_amplitude;
            draw_eyes();
            delay(1);
        }

        for (int i = 0; i < 1; i++) {
            left_eye_x += direction_x_movement_amplitude * direction_x;
            right_eye_x += direction_x_movement_amplitude * direction_x;
            left_eye_y += direction_y_movement_amplitude * direction_y;
            right_eye_y += direction_y_movement_amplitude * direction_y;

            right_eye_height += blink_amplitude;
            left_eye_height += blink_amplitude;

            draw_eyes();
            delay(1);
        }
    }



    void move_big_eye(int direction) {
        static int step = 0;
        static unsigned long last_update = 0;
        static bool in_progress = false;

        if (!in_progress) {
            step = 0;
            last_update = millis();
            in_progress = true;
            animation_in_progress = true;
        }

        unsigned long current_time = millis();
        int direction_oversize = 1;
        int direction_movement_amplitude = 2;
        int blink_amplitude = 5;
        int interval = 1; // Delay interval

        if (current_time - last_update >= interval) {
            last_update = current_time;

            switch (step) {
                case 0:
                case 1:
                case 2:
                    left_eye_x += direction_movement_amplitude * direction;
                    right_eye_x += direction_movement_amplitude * direction;
                    right_eye_height -= blink_amplitude;
                    left_eye_height -= blink_amplitude;
                    if (direction > 0) {
                        right_eye_height += direction_oversize;
                        right_eye_width += direction_oversize;
                    } else {
                        left_eye_height += direction_oversize;
                        left_eye_width += direction_oversize;
                    }
                    draw_eyes();
                    step++;
                    break;

                case 3:
                case 4:
                case 5:
                    left_eye_x += direction_movement_amplitude * direction;
                    right_eye_x += direction_movement_amplitude * direction;
                    right_eye_height += blink_amplitude;
                    left_eye_height += blink_amplitude;
                    if (direction > 0) {
                        right_eye_height += direction_oversize;
                        right_eye_width += direction_oversize;
                    } else {
                        left_eye_height += direction_oversize;
                        left_eye_width += direction_oversize;
                    }
                    draw_eyes();
                    step++;
                    break;

                case 6:
                    delay(1000); // Pause for a second before moving back
                    step++;
                    break;

                case 7:
                case 8:
                case 9:
                    left_eye_x -= direction_movement_amplitude * direction;
                    right_eye_x -= direction_movement_amplitude * direction;
                    right_eye_height -= blink_amplitude;
                    left_eye_height -= blink_amplitude;
                    if (direction > 0) {
                        right_eye_height -= direction_oversize;
                        right_eye_width -= direction_oversize;
                    } else {
                        left_eye_height -= direction_oversize;
                        left_eye_width -= direction_oversize;
                    }
                    draw_eyes();
                    step++;
                    break;

                case 10:
                case 11:
                case 12:
                    left_eye_x -= direction_movement_amplitude * direction;
                    right_eye_x -= direction_movement_amplitude * direction;
                    right_eye_height += blink_amplitude;
                    left_eye_height += blink_amplitude;
                    if (direction > 0) {
                        right_eye_height -= direction_oversize;
                        right_eye_width -= direction_oversize;
                    } else {
                        left_eye_height -= direction_oversize;
                        left_eye_width -= direction_oversize;
                    }
                    draw_eyes();
                    step++;
                    break;

                case 13:
                    center_eyes();
                    in_progress = false;
                    animation_in_progress = false;
                    break;
            }
        }
    }


    void move_right_big_eye() {
        move_big_eye(1);
    }

    void move_left_big_eye() {
        move_big_eye(-1);
    }









    void performTimedTasks() {
        static int currentStage = 0;
        happy_eye();
/*
        switch (currentStage) {
            case 0:
                wakeup();
                if (!animation_in_progress) currentStage++;
                break;
            case 1:
                center_eyes(true, 1500);
                if (!animation_in_progress) currentStage++;
                break;
            case 2:
                blink();
                if (!animation_in_progress) currentStage++;
                break;
            case 3:
                center_eyes(true, 500);
                if (!animation_in_progress) currentStage++;
                break;
            case 4:
                center_eyes(true, 500);
                if (!animation_in_progress) currentStage++;
                break;
            case 5:
                blink();
                if (!animation_in_progress) currentStage++;
                break;
            case 6:
                center_eyes(true, 500);
                if (!animation_in_progress) currentStage++;
                break;
            case 7:
                sleep();
                if (!animation_in_progress) currentStage = 0; // Loop back to the start
                break;
        }
*/

    }

}

#endif // EYES_ANIMATION_H