# animations/base.py
# Minimal plugin API for Mochi animations.

from typing import Optional, Tuple
from core.gfx import parse_color

def clamp8(v: int) -> int:
    return 0 if v < 0 else 255 if v > 255 else v


class Animation:
    """Base class every animation must implement."""

    name: str = "unnamed"

    def __init__(self, w: int, h: int):
        self.w = int(w)
        self.h = int(h)
        self.fg: Tuple[int, int, int] = (235, 235, 255)  # default accent color
        self.clear_on_frame: bool = True # Default behavior is to clear the screen

    # ---- lifecycle hooks ----
    def on_enter(self, **kwargs) -> None:
        """Called when the animation becomes active."""
        if "fg" in kwargs:
            self.set_color(parse_color(kwargs["fg"], self.fg))
        
        # Allow scripts to control the screen clearing behavior
        if "clear" in kwargs and isinstance(kwargs["clear"], bool):
            self.clear_on_frame = kwargs["clear"]

    def on_event(self, event: str, **kwargs) -> None:
        """Optional external nudges (e.g., 'blink', 'smile')."""
        pass

    # ---- runtime config ----
    def set_size(self, w: int, h: int) -> None:
        self.w, self.h = int(w), int(h)

    def set_color(self, color: Tuple[int, int, int]) -> None:
        self.fg = color

    # ---- required per-frame render ----
    def render_into(self, t: float, pixel_buf: bytearray):
        """Render the animation frame into the provided buffer."""
        raise NotImplementedError
