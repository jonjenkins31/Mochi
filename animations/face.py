# animations/face.py
# Mochi-style face (eyes + pupils + occasional blink + simple mouth VU).
import math, random, time
from .base import Animation, clamp8


class Face(Animation):
    name = "face"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        # palette
        self.eye_white = (235, 235, 255)
        self.pupil_col = (25, 25, 40)
        self.lid_col   = (230, 230, 240)
        self.bg_base   = (8, 8, 12)
        self.mouth_col = (255, 120, 120)

        # dynamics
        self._next_blink_t = time.time() + random.uniform(3.0, 7.0)
        self._blink_dur = 0.12
        self._blink_end_t = None

        # external “energy” for mouth openness (0..1)
        self.vu = 0.25

    # Optional external nudges
    def on_event(self, event: str, **kwargs):
        e = event.lower()
        if e == "blink":
            now = time.time()
            # trigger a blink immediately
            self._blink_end_t = now + self._blink_dur
            self._next_blink_t = now + random.uniform(3.0, 7.0)
        elif e == "vu":
            # allow 'event vu value=0.6' from scripts
            v = kwargs.get("value")
            if v is not None:
                try: self.vu = max(0.0, min(1.0, float(v)))
                except Exception: pass

    def frame(self, t: float) -> bytes:
        w, h = self.w, self.h
        buf = bytearray(w*h*3)

        # --- background with gentle “breathing” tint ---
        breath = (math.sin(t*0.8)*0.5+0.5)*0.12
        tint_b = int(12 + (15 + breath*80))
        r0, g0, b0 = self.bg_base
        b0 = clamp8(tint_b)
        for i in range(0, len(buf), 3):
            buf[i:i+3] = (r0, g0, b0)

        def put(x, y, rgb):
            if 0 <= x < w and 0 <= y < h:
                i = (y*w + x)*3
                buf[i:i+3] = bytes((clamp8(rgb[0]), clamp8(rgb[1]), clamp8(rgb[2])))

        # --- geometry for eyes ---
        eye_y  = h//2 - 2
        eye_dx = max(1, w//6)
        lx, rx = w//2 - eye_dx, w//2 + eye_dx
        r_eye  = max(2, w//10)

        # Blink timing
        now = t
        if self._blink_end_t is None and (time.time() >= self._next_blink_t):
            self._blink_end_t = time.time() + self._blink_dur

        blink_amt = 0.0
        if self._blink_end_t is not None:
            # 0→1 over blink duration
            phase = 1.0 - max(0.0, (self._blink_end_t - time.time())/self._blink_dur)
            blink_amt = max(0.0, min(1.0, phase))
            if time.time() >= self._blink_end_t:
                self._blink_end_t = None
                self._next_blink_t = time.time() + random.uniform(3.0, 7.0)

        # --- draw eyes (two discs) ---
        r2 = r_eye*r_eye
        for y in range(max(0, eye_y-r_eye), min(h, eye_y+r_eye+1)):
            dy2 = (y-eye_y)*(y-eye_y)
            # left eye
            x0 = max(0, lx-r_eye)
            x1 = min(w, lx+r_eye+1)
            for x in range(x0, x1):
                if (x-lx)*(x-lx) + dy2 <= r2:
                    put(x, y, self.eye_white)
            # right eye
            x0 = max(0, rx-r_eye)
            x1 = min(w, rx+r_eye+1)
            for x in range(x0, x1):
                if (x-rx)*(x-rx) + dy2 <= r2:
                    put(x, y, self.eye_white)

        # eyelid line (blink)
        if blink_amt > 0:
            lid_y = eye_y + int(blink_amt*1.0)
            for x in range(max(0, lx-r_eye), min(w, lx+r_eye+1)):
                put(x, lid_y, self.lid_col)
            for x in range(max(0, rx-r_eye), min(w, rx+r_eye+1)):
                put(x, lid_y, self.lid_col)

        # pupils
        pr = max(1, r_eye-2)
        for dy in range(-pr, pr+1):
            yy = eye_y+dy
            if 0 <= yy < h:
                row_r2 = pr*pr - dy*dy
                # left/right pupils
                for dx in range(-pr, pr+1):
                    if dx*dx <= row_r2:
                        put(lx+dx, yy, self.pupil_col)
                        put(rx+dx, yy, self.pupil_col)

        # --- mouth (simple bar, open by VU) ---
        mouth_y = h//2 + r_eye + 2
        width   = w//4
        # subtle auto VU breathing if none provided
        vu = self.vu if self.vu is not None else (math.sin(t*3.1)*0.5+0.5)*0.5
        open_amt = max(1, min(h//6, 1 + int(vu*4)))
        for y in range(open_amt):
            yy = mouth_y + y
            if 0 <= yy < h:
                xL = w//2 - width//2
                xR = w//2 + width//2
                for x in range(xL, xR):
                    put(x, yy, self.mouth_col)

        return bytes(buf)