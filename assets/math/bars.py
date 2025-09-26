# assets/math/bars.py
# Vertical sweeping bars using a sinusoidal profile.

import numpy as np
from core.mochi_animations import Animation


class Bars(Animation):
    name = "bars"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.speed = 2.0     # radians/sec for phase advance
        self.x_scale = 0.30  # spatial frequency along X
        self._x_coords = None
        self._rebuild_coords()

    def _rebuild_coords(self):
        self._x_coords = np.arange(self.w)

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        self.speed = float(kwargs.get("speed", self.speed))
        self.x_scale = float(kwargs.get("x_scale", self.x_scale))

    def set_size(self, w: int, h: int):
        super().set_size(w, h)
        self._rebuild_coords()

    def render_into(self, t: float, pixel_buf: bytearray):
        # Create a NumPy array that shares memory with the pixel buffer (no copy)
        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))

        # Calculate the brightness value `v` for all columns at once.
        v = np.sin(t * self.speed + self._x_coords * self.x_scale) * 0.5 + 0.5  # Shape: (w,)

        # Use NumPy broadcasting to multiply the foreground color by the brightness values.
        # This creates a single row of colors. Shape: (w, 3)
        colors = v[:, np.newaxis] * np.array(self.fg)

        # Assign the calculated row to all rows of the frame. NumPy handles the tiling automatically.
        frame[:, :, :] = colors.astype(np.uint8)
