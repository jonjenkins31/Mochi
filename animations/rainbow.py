# animations/rainbow.py
# Rainbow flow using three phase-shifted sinusoids (fast, branchless, pretty).

import math
from .base import Animation


class Rainbow(Animation):
    name = "rainbow"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.speed = 20.0  # pixels/sec flow to the right

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        self.speed = float(kwargs.get("speed", self.speed))

    def frame(self, t: float) -> bytes:
        w, h = self.w, self.h
        buf = self._blank(r=0, g=0, b=0)
        # Precompute phase per column
        for y in range(h):
            for x in range(w):
                u = (x + t * self.speed) / max(1, w)
                # 2π/3 phase shifts (~2.094, 4.188)
                r = int((math.sin(2 * math.pi * u) + 1.0) * 127.5)
                g = int((math.sin(2 * math.pi * u + 2.094) + 1.0) * 127.5)
                b = int((math.sin(2 * math.pi * u + 4.188) + 1.0) * 127.5)
                i = (y * w + x) * 3
                buf[i : i + 3] = bytes((r, g, b))
        return bytes(buf)