# animations/media_player.py
from __future__ import annotations
from typing import Optional, List, Tuple
from .base import Animation
from core.media import MediaFrames, decode_image

class MediaPlayer(Animation):
    """
    Plays a raster image, GIF/APNG (animated), or SVG (requires cairosvg).
    By default uses GIF/APNG per-frame durations; can override with fps.
    """
    name = "media_player"

    def __init__(self, w:int, h:int, frames: Optional[MediaFrames] = None):
        super().__init__(w, h)
        self._mf: Optional[MediaFrames] = frames
        self._loop = True
        self._fps_override: Optional[float] = None  # if set, ignore durations
        self._letterbox = (0,0,0)

    def on_enter(self, **kw):
        super().on_enter(**kw)
        # You can pass: path=..., fps=..., loop=..., fit='fit'|'fill'|'stretch', bg=[r,g,b]
        path = kw.get("path")
        fit = kw.get("fit", "fit")
        self._loop = bool(kw.get("loop", True))
        self._fps_override = float(kw["fps"]) if "fps" in kw else None
        if "bg" in kw:
            self._letterbox = tuple(kw["bg"])
        if path and not self._mf:
            self._mf = decode_image(path, target_size=(self.w, self.h), fit_mode=fit, letterbox_color=self._letterbox)

    # Zero-copy path
    def render_into(self, t: float, out_buf: bytearray) -> None:
        if not self._mf or not self._mf.frames:
            # fill blank
            out_buf[:] = b"\x00" * len(out_buf)
            return

        idx = 0
        if self._fps_override and self._fps_override > 0:
            period = 1.0 / self._fps_override
            idx = int(t / period) % len(self._mf.frames) if self._loop else min(int(t/period), len(self._mf.frames)-1)
        else:
            # use durations; treat 0 as 100ms default
            # accumulate elapsed ≈ t*1000 ms
            elapsed = int(t * 1000.0)
            total = 0
            for i, d in enumerate(self._mf.durations_ms):
                dur = d if d > 0 else 100
                if elapsed < total + dur:
                    idx = i; break
                total += dur
            else:
                if self._loop:
                    elapsed %= max(1, total)
                    total = 0
                    for i, d in enumerate(self._mf.durations_ms):
                        dur = d if d > 0 else 100
                        if elapsed < total + dur:
                            idx = i; break
                        total += dur
                else:
                    idx = len(self._mf.frames) - 1

        im = self._mf.frames[idx]
        # im is already RGB and sized to (w,h)
        mv = memoryview(out_buf)
        mv[:] = im.tobytes()

    # Back-compat
    def frame(self, t: float) -> bytes:
        buf = bytearray(self.w*self.h*3)
        self.render_into(t, buf)
        return bytes(buf)