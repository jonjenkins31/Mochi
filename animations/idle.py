from .base import Animation
import math

class Idle(Animation):
    name = "idle"
    def frame(self, t):
        w, h = self.w, self.h
        buf = bytearray(w*h*3)
        breath = (math.sin(t*0.8)*0.5+0.5)*0.12
        tint = int(15 + breath*80)
        for i in range(0, len(buf), 3):
            buf[i:i+3] = (8, 8, min(255, 12 + tint))
        # (you can draw eyes here too)
        return bytes(buf)