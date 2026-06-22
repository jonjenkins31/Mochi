from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np

from plugin_core.mochi_animations import Animation
from .decoders import MediaFrames, normalize_letterbox_color


class DecodedMediaAnimation(Animation):
    """Base animation helper that renders decoded media frames."""

    name: str | None = None
    DEFAULT_FIT = "fit"
    DEFAULT_LOOP = False
    DEFAULT_SPEED = 1.0
    supports_loop = True
    supports_speed = True

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self._frames: Optional[MediaFrames] = None
        self.asset_path: str | None = None
        self.fit_mode: str = self.DEFAULT_FIT
        self._letterbox = (0, 0, 0)
        self._loop = self.DEFAULT_LOOP
        self.speed = self.DEFAULT_SPEED
        self._start_time: float | None = None

    # ------------------------------------------------------------------ hooks
    def decode(
        self,
        path: str,
        *,
        target_size: tuple[int, int],
        fit_mode: str,
        letterbox: tuple[int, int, int],
    ) -> Optional[MediaFrames]:
        raise NotImplementedError

    def _target_size(self) -> tuple[int, int]:
        return (self.w, self.h)

    # ---------------------------------------------------------------- lifecycle
    def on_enter(self, **kw):
        super().on_enter(**kw)
        asset_value = kw.get("asset_path")
        resolve_dir = kw.get("resolve_dir")

        asset_path: str | None
        if asset_value is None:
            asset_path = None
        else:
            asset_path_obj = Path(asset_value)
            if not asset_path_obj.is_absolute() and resolve_dir:
                asset_path_obj = Path(resolve_dir) / asset_path_obj
            asset_path = os.fspath(asset_path_obj)

        self.asset_path = asset_path
        self.fit_mode = kw.get("fit", self.DEFAULT_FIT)
        self._letterbox = normalize_letterbox_color(kw.get("BG"))
        self._start_time = None

        if self.supports_loop:
            self._loop = bool(kw.get("loop", self.DEFAULT_LOOP))
        else:
            self._loop = False

        if self.supports_speed:
            try:
                self.speed = float(kw.get("SPD", self.DEFAULT_SPEED))
            except (TypeError, ValueError):
                self.speed = self.DEFAULT_SPEED
        else:
            self.speed = 1.0

        self._load_frames()

    def set_size(self, w: int, h: int):
        super().set_size(w, h)
        if self.asset_path:
            self._load_frames()

    # ----------------------------------------------------------------- helpers
    def _load_frames(self):
        if not self.asset_path:
            self._frames = None
            return
        frames = self.decode(
            self.asset_path,
            target_size=self._target_size(),
            fit_mode=self.fit_mode,
            letterbox=self._letterbox,
        )
        self._frames = frames

    # ---------------------------------------------------------------- renderer
    def render_into(self, t: float, out_buf: bytearray) -> None:
        frames = self._frames
        if not frames or not frames.frames:
            out_buf[:] = b"\x00" * len(out_buf)
            return
        elapsed_ms = self._elapsed_ms(t)
        frame_idx = self._select_frame_index(frames, elapsed_ms)
        frame = frames.frames[frame_idx]

        frame_np = np.frombuffer(out_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        frame_np[:, :] = np.asarray(frame)

    def _elapsed_ms(self, t: float) -> int:
        if self._start_time is None:
            self._start_time = t
        elapsed = max(0.0, t - self._start_time)
        speed = self.speed if self.supports_speed else 1.0
        return int(elapsed * 1000.0 * speed)

    def _select_frame_index(self, frames: MediaFrames, elapsed_ms: int) -> int:
        if frames.frame_count <= 1:
            return 0

        total_duration = frames.total_duration

        if self._loop and total_duration > 0:
            elapsed_ms %= total_duration

        current_duration = 0
        for idx, duration in enumerate(frames.durations_ms):
            dur = duration if duration > 0 else 100
            if elapsed_ms < current_duration + dur:
                return idx
            current_duration += dur

        return frames.frame_count - 1
