# animations/media_player.py
from __future__ import annotations
from typing import Optional, List, Tuple
import numpy as np
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
        self._fps_override: Optional[float] = None
        self._letterbox = (0,0,0)
        # Store path and fit mode for resizing
        self.path: Optional[str] = None
        self.fit_mode: str = "fit"

    def on_enter(self, **kw):
        super().on_enter(**kw)
        path = kw.get("path")
        self.fit_mode = kw.get("fit", "fit")
        self._loop = bool(kw.get("loop", True))
        self._fps_override = float(kw["fps"]) if "fps" in kw else None
        if "bg" in kw:
            self._letterbox = tuple(kw["bg"])
        
        if path:
            self.path = path # Remember the path
            if not self._mf:
                self._mf = decode_image(self.path, target_size=(self.w, self.h), fit_mode=self.fit_mode, letterbox_color=self._letterbox)

    def set_size(self, w: int, h: int):
        super().set_size(w, h)
        # If we are playing a file, we must re-decode it at the new size.
        if self.path:
            self._mf = decode_image(self.path, target_size=(self.w, self.h), fit_mode=self.fit_mode, letterbox_color=self._letterbox)

    def render_into(self, t: float, out_buf: bytearray) -> None:
        if not self._mf or not self._mf.frames:
            out_buf[:] = b"\x00" * len(out_buf)
            return

        idx = 0
        if self._fps_override and self._fps_override > 0:
            period = 1.0 / self._fps_override
            idx = int(t / period) % len(self._mf.frames) if self._loop else min(int(t/period), len(self._mf.frames)-1)
        else:
            elapsed = int(t * 1000.0)
            total_duration = self._mf.total_duration
            if self._loop and total_duration > 0:
                elapsed %= total_duration
            
            current_duration = 0
            for i, d in enumerate(self._mf.durations_ms):
                dur = d if d > 0 else 100
                if elapsed < current_duration + dur:
                    idx = i
                    break
                current_duration += dur
            else:
                idx = len(self._mf.frames) - 1

        im = self._mf.frames[idx]
        
        frame = np.frombuffer(out_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        frame[:, :] = np.asarray(im)
