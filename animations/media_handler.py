# animations/media_handler.py

"""
Media Handler: The Generic Image & GIF Player

Function:
This handler is responsible for displaying standard raster images (PNG, JPG, BMP)
and animated GIFs. It is invoked by the Master Handler for a 'MEDIA' command.
It handles image decoding, resizing (including letterboxing), and frame
timing for animations.

Inputs (via kwargs from Master Handler):
- asset_path (str): The absolute path to the image or GIF file to be displayed.
- SPD (float, optional): Playback speed multiplier for animated GIFs.
  Defaults to 1.0.
- BG (list[int], optional): The RGB color for letterboxing.
  Defaults to black.
- loop (bool, optional): For animated GIFs, determines if the animation should
  loop. Defaults to True.

Output:
- Renders the image or the correct animation frame into the pixel buffer
  provided by the Mochi node.
"""

from __future__ import annotations
from typing import Optional
import numpy as np
from core.mochi_animations import Animation
from core.media import MediaFrames, decode_image

class MediaHandler(Animation):
    """
    Plays a raster image or animated media (GIF/APNG).
    Supports speed control and letterboxing.
    """
    name = "MEDIA"

    def __init__(self, w:int, h:int, frames: Optional[MediaFrames] = None):
        super().__init__(w, h)
        self._mf: Optional[MediaFrames] = frames
        self._loop = True
        self._letterbox = (0,0,0)
        self.speed = 1.0
        # Store path and fit mode for resizing
        self.path: Optional[str] = None
        self.fit_mode: str = "fit"

    def on_enter(self, **kw):
        super().on_enter(**kw)
        path = kw.get("asset_path")
        self.fit_mode = kw.get("fit", "fit")
        self._loop = bool(kw.get("loop", True))
        self.speed = float(kw.get("SPD", 1.0))

        if "BG" in kw and isinstance(kw["BG"], list):
            self._letterbox = tuple(kw["BG"])
        
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

        # Apply speed multiplier to time
        effective_t = t * self.speed

        idx = 0
        elapsed = int(effective_t * 1000.0)
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
