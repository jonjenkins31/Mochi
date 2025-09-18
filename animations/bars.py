# animations/bars.py
# Vertical sweeping bars using a sinusoidal profile.

import math
from .base import Animation


class Bars(Animation):
    name = "bars"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.speed = 2.0     # radians/sec for phase advance
        self.x_scale = 0.30  # spatial frequency along X

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        self.speed = float(kwargs.get("speed", self.speed))
        self.x_scale = float(kwargs.get("x_scale", self.x_scale))

    def frame(self, t: float) -> bytes:
        buf = self._blank(r=8, g=8, b=12)
        r0, g0, b0 = self.fg
        w, h = self.w, self.h
        # Sweep along X with time-based phase
        for x in range(w):
            v = math.sin(t * self.speed + x * self.x_scale) * 0.5 + 0.5  # [0..1]
            col = (int(r0 * v), int(g0 * v), int(b0 * v))
            for y in range(h):
                i = (y * w + x) * 3
                buf[i : i + 3] = bytes(col)
        return bytes(buf)