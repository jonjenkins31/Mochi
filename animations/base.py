# animations/base.py
# Minimal plugin API for Mochi animations.

from typing import Optional, Tuple


def clamp8(v: int) -> int:
    return 0 if v < 0 else 255 if v > 255 else v


class Animation:
    """Base class every animation must implement."""

    name: str = "unnamed"

    def __init__(self, w: int, h: int):
        self.w = int(w)
        self.h = int(h)
        self.fg: Tuple[int, int, int] = (235, 235, 255)  # default accent color

    # ---- lifecycle hooks ----
    def on_enter(self, **kwargs) -> None:
        """Called when the animation becomes active."""
        fg = kwargs.get("fg")
        if fg:
            self.set_color(*fg)

    def on_event(self, event: str, **kwargs) -> None:
        """Optional external nudges (e.g., 'blink', 'smile')."""
        pass

    # ---- runtime config ----
    def set_size(self, w: int, h: int) -> None:
        self.w, self.h = int(w), int(h)

    def set_color(self, r: int, g: int, b: int) -> None:
        self.fg = (clamp8(int(r)), clamp8(int(g)), clamp8(int(b)))

    # ---- required per-frame render ----
    def frame(self, t: float) -> bytes:
        """Return raw RGB bytes (w*h*3) for the current frame time t (seconds)."""
        raise NotImplementedError

    # ---- helpers ----
    def _blank(self, r=8, g=8, b=12) -> bytearray:
        """Make a background buffer (breathing/other effects can override in subclasses)."""
        return bytearray([r, g, b] * (self.w * self.h))

    def _put(self, buf: bytearray, x: int, y: int, rgb: Tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            r, g, b = rgb
            buf[i : i + 3] = bytes((clamp8(r), clamp8(g), clamp8(b)))