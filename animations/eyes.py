
import time
import numpy as np
from .base import Animation
from core.gfx import fill_round_rect

class Eyes(Animation):
    name = "eyes"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        # Eye geometry
        self.eye_w = 20
        self.eye_h = 20
        self.eye_spacing = 4
        self.corner_radius = 4

        # Initial state
        self.center_x = self.w / 2
        self.center_y = self.h / 2
        self.left_eye_pos = (self.center_x - self.eye_w / 2 - self.eye_spacing, self.center_y)
        self.right_eye_pos = (self.center_x + self.eye_w / 2 + self.eye_spacing, self.center_y)
        self.left_eye_size = (self.eye_w, self.eye_h)
        self.right_eye_size = (self.eye_w, self.eye_h)

        # Animation state
        self.anim_mode = None
        self.anim_start_t = 0

    def on_enter(self, **kwargs):
        super().on_enter(**kwargs)
        self.center_eyes() # Reset to default state

    def on_event(self, event: str, **kwargs):
        self.anim_mode = event.lower()
        self.anim_start_t = time.time()

    def render_into(self, t: float, pixel_buf: bytearray):
        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        frame[:, :] = (0, 0, 0)  # Clear to black

        if self.anim_mode and self.anim_mode != "hold":
            elapsed = t - self.anim_start_t
            handler = getattr(self, f"_anim_{self.anim_mode}", None)
            if handler:
                handler(elapsed)
            else:
                self.center_eyes() # Default to center if anim is unknown

        # Draw the two eyes
        lx, ly = self.left_eye_pos
        lw, lh = self.left_eye_size
        fill_round_rect(frame, int(lx - lw/2), int(ly - lh/2), int(lw), int(lh), self.corner_radius, self.fg)

        rx, ry = self.right_eye_pos
        rw, rh = self.right_eye_size
        fill_round_rect(frame, int(rx - rw/2), int(ry - rh/2), int(rw), int(rh), self.corner_radius, self.fg)

    def center_eyes(self):
        self.left_eye_pos = (self.center_x - self.eye_w / 2 - self.eye_spacing, self.center_y)
        self.right_eye_pos = (self.center_x + self.eye_w / 2 + self.eye_spacing, self.center_y)
        self.left_eye_size = (self.eye_w, self.eye_h)
        self.right_eye_size = (self.eye_w, self.eye_h)
        self.anim_mode = None

    def _anim_wakeup(self, elapsed: float, duration=1.5):
        p = min(elapsed / duration, 1.0)
        
        if p < 0.4: # Stage 1: Expand width
            w = self.eye_w * (p / 0.4)
            self.left_eye_size = (w, 2)
            self.right_eye_size = (w, 2)
        elif p < 0.5: # Stage 2: Hold horizontal line
            self.left_eye_size = (self.eye_w, 2)
            self.right_eye_size = (self.eye_w, 2)
        elif p < 0.9: # Stage 3: Expand height
            h_p = (p - 0.5) / 0.4
            h = 2 + (self.eye_h - 2) * h_p
            self.left_eye_size = (self.eye_w, h)
            self.right_eye_size = (self.eye_w, h)
        else: # Stage 4: Hold open
            self.left_eye_size = (self.eye_w, self.eye_h)
            self.right_eye_size = (self.eye_w, self.eye_h)

        if p >= 1.0: self.center_eyes()

    def _anim_sleep(self, elapsed: float, duration=1.5):
        p = min(elapsed / duration, 1.0)

        if p < 0.4: # Stage 1: Shrink height
            h = self.eye_h * (1.0 - (p / 0.4))
            self.left_eye_size = (self.eye_w, h)
            self.right_eye_size = (self.eye_w, h)
        elif p < 0.5: # Stage 2: Hold horizontal line
            self.left_eye_size = (self.eye_w, 2)
            self.right_eye_size = (self.eye_w, 2)
        elif p < 0.9: # Stage 3: Shrink width
            w_p = (p - 0.5) / 0.4
            w = self.eye_w * (1.0 - w_p)
            self.left_eye_size = (w, 2)
            self.right_eye_size = (w, 2)
        else: # Stage 4: Hold closed
            self.left_eye_size = (0, 0)
            self.right_eye_size = (0, 0)

        if p >= 1.0:
            self.left_eye_size = (0, 0)
            self.right_eye_size = (0, 0)
            self.anim_mode = None # Stay asleep

    def _anim_blink(self, elapsed: float, duration=0.25):
        p = min(elapsed / duration, 1.0)
        if p < 0.5:
            h = self.eye_h * (1.0 - (p * 2))
        else:
            h = self.eye_h * ((p - 0.5) * 2)
        self.left_eye_size = (self.eye_w, h)
        self.right_eye_size = (self.eye_w, h)
        if p >= 1.0: self.center_eyes()

    def _anim_look_left(self, elapsed: float, duration=0.4):
        p = min(elapsed / duration, 1.0)
        offset = -10 * p
        self.left_eye_pos = (self.center_x - self.eye_w / 2 - self.eye_spacing + offset, self.center_y)
        self.right_eye_pos = (self.center_x + self.eye_w / 2 + self.eye_spacing + offset, self.center_y)
        if p >= 1.0: self.anim_mode = "hold" # Stay looking left

    def _anim_look_right(self, elapsed: float, duration=0.4):
        p = min(elapsed / duration, 1.0)
        offset = 10 * p
        self.left_eye_pos = (self.center_x - self.eye_w / 2 - self.eye_spacing + offset, self.center_y)
        self.right_eye_pos = (self.center_x + self.eye_w / 2 + self.eye_spacing + offset, self.center_y)
        if p >= 1.0: self.anim_mode = "hold" # Stay looking right

    def _anim_center(self, elapsed: float, duration=0.3):
        p = min(elapsed / duration, 1.0)
        # A simple interpolation back to center.
        current_offset = self.left_eye_pos[0] - (self.center_x - self.eye_w / 2 - self.eye_spacing)
        offset = current_offset * (1.0 - p)
        self.left_eye_pos = (self.center_x - self.eye_w / 2 - self.eye_spacing + offset, self.center_y)
        self.right_eye_pos = (self.center_x + self.eye_w / 2 + self.eye_spacing + offset, self.center_y)
        if p >= 1.0: self.center_eyes()
