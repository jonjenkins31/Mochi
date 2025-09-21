# animations/test_fast_lines.py
# A Python/NumPy recreation of the testFastLines pattern from Adafruit GFX.

import numpy as np
from .base import Animation
from core.gfx import parse_color

class TestFastLines(Animation):
    name = "test_fast_lines"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.color1 = (255, 0, 0)  # Default to Red
        self.color2 = (0, 0, 255)  # Default to Blue

    def on_enter(self, **kwargs):
        super().on_enter(**kwargs) # Handles the 'clear' flag
        
        if "color1" in kwargs:
            self.color1 = parse_color(kwargs["color1"], self.color1)
        if "color2" in kwargs:
            self.color2 = parse_color(kwargs["color2"], self.color2)

    def render_into(self, t: float, pixel_buf: bytearray):
        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        
        if self.clear_on_frame:
            frame[:, :] = (0, 0, 0)  # Clear to black

        # Draw horizontal lines
        for y in range(0, self.h, 5):
            frame[y, :] = self.color1

        # Draw vertical lines
        for x in range(0, self.w, 5):
            frame[:, x] = self.color2
