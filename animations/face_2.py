# animations/face_2.py
# Variant of the original inline face animation (breathing bg, eyes, blink, pupils, mouth).

import math, random, time
from .base import Animation, clamp8


class Face2(Animation):
    name = "face_2"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        # palette (kept identical to original inline version)
        self.eye_white = (235, 235, 255)
        self.pupil_col = (25, 25, 40)
        self.lid_col   = (230, 230, 240)
        self.bg_base   = (8, 8, 12)
        self.mouth_col = (255, 120, 120)

        # blink timing (same cadence as original)
        self._next_blink_t = time.time() + random.uniform(3.0, 7.0)
        self._blink_dur = 0.12
        self._blink_end_t = None

    # Optional external nudges
    def on_event(self, event: str, **kwargs):
        e = (event or "").lower()
        if e == "blink":
            now = time.time()
            self._blink_end_t = now + self._blink_dur
            self._next_blink_t = now + random.uniform(3.0, 7.0)

    def frame(self, t: float) -> bytes:
        w, h = self.w, self.h
        buf = bytearray(w*h*3)

        # --- breathing background (identical math to original) ---
        breath = (math.sin(t*0.8)*0.5 + 0.5) * 0.12
        tint_b = clamp8(int(12 + (15 + breath*80)))
        r0, g0, b0 = self.bg_base
        for i in range(0, len(buf), 3):
            buf[i:i+3] = (r0, g0, tint_b)

        def put(x, y, rgb):
            if 0 <= x < w and 0 <= y < h:
                i = (y*w + x)*3
                r, g, b = rgb
                buf[i:i+3] = bytes((clamp8(r), clamp8(g), clamp8(b)))

        # --- geometry (same as original) ---
        eye_y  = h//2 - 2
        eye_dx = max(1, w//6)
        lx, rx = w//2 - eye_dx, w//2 + eye_dx
        r_eye  = max(2, w//10)

        # Blink timing (same linear close/open over duration)
        now_real = time.time()
        if self._blink_end_t is None and now_real >= self._next_blink_t:
            self._blink_end_t = now_real + self._blink_dur

        blink_amt = 0.0
        if self._blink_end_t is not None:
            phase = 1.0 - max(0.0, (self._blink_end_t - now_real)/self._blink_dur)
            blink_amt = max(0.0, min(1.0, phase))
            if now_real >= self._blink_end_t:
                self._blink_end_t = None
                self._next_blink_t = now_real + random.uniform(3.0, 7.0)

        # --- eyes (two discs) ---
        r2 = r_eye*r_eye
        y_top = max(0, eye_y - r_eye)
        y_bot = min(h, eye_y + r_eye + 1)
        for y in range(y_top, y_bot):
            dy2 = (y - eye_y) * (y - eye_y)
            # left eye
            xL0 = max(0, lx - r_eye)
            xL1 = min(w, lx + r_eye + 1)
            for x in range(xL0, xL1):
                if (x - lx) * (x - lx) + dy2 <= r2:
                    put(x, y, self.eye_white)
            # right eye
            xR0 = max(0, rx - r_eye)
            xR1 = min(w, rx + r_eye + 1)
            for x in range(xR0, xR1):
                if (x - rx) * (x - rx) + dy2 <= r2:
                    put(x, y, self.eye_white)

        # eyelid line (blink)
        if blink_amt > 0:
            lid_y = eye_y + int(blink_amt * 1.0)
            for x in range(max(0, lx - r_eye), min(w, lx + r_eye + 1)):
                put(x, lid_y, self.lid_col)
            for x in range(max(0, rx - r_eye), min(w, rx + r_eye + 1)):
                put(x, lid_y, self.lid_col)

        # pupils (filled small discs)
        pr = max(1, r_eye - 2)
        for dy in range(-pr, pr + 1):
            yy = eye_y + dy
            if 0 <= yy < h:
                row_r2 = pr*pr - dy*dy
                for dx in range(-pr, pr + 1):
                    if dx*dx <= row_r2:
                        put(lx + dx, yy, self.pupil_col)
                        put(rx + dx, yy, self.pupil_col)

        # --- mouth (same rectangular “open” amount driven by a soft VU) ---
        mouth_y = h//2 + r_eye + 2
        width   = w//4
        vu = (math.sin(t*3.1) * 0.5 + 0.5) * 0.5  # matches the original vibe
        open_amt = int(min(h//6, 1 + int(vu * 4)))
        for y in range(open_amt):
            yy = mouth_y + y
            if 0 <= yy < h:
                xL = w//2 - width//2
                xR = w//2 + width//2
                for x in range(xL, xR):
                    put(x, yy, self.mouth_col)

        return bytes(buf)