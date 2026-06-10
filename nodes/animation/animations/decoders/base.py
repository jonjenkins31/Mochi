from __future__ import annotations

import logging
from typing import Iterable, List, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


class MediaFrames:
    """Container for decoded frames and their per-frame durations (milliseconds)."""

    def __init__(self, frames: List[Image.Image], durations_ms: List[int]):
        self.frames: List[Image.Image] = frames
        self.durations_ms: List[int] = durations_ms
        self.total_duration: int = sum(d if d > 0 else 100 for d in self.durations_ms)

    @property
    def frame_count(self) -> int:
        return len(self.frames)


def normalize_letterbox_color(color: Iterable[int] | None) -> Tuple[int, int, int]:
    """Normalizes an RGB color iterable to a tuple of ints, defaulting to black."""
    if not color:
        return (0, 0, 0)
    try:
        r, g, b = list(color)[:3]
    except Exception:  # pragma: no cover - defensive guard
        logger.warning("Invalid letterbox color %r, defaulting to (0, 0, 0)", color)
        return (0, 0, 0)
    return (int(r), int(g), int(b))


def ensure_rgb(image: Image.Image) -> Image.Image:
    """Ensures the Pillow image is in RGB mode."""
    if image.mode == "RGB":
        return image
    return image.convert("RGB")


def resize_frame(
    frame: Image.Image,
    target_size: Tuple[int, int],
    fit_mode: str,
    letterbox_color: Tuple[int, int, int],
) -> Image.Image:
    """Resizes a frame to the target size using the requested fit mode."""
    if frame.size == target_size:
        return frame

    w_target, h_target = target_size
    resample_filter = Image.NEAREST

    if fit_mode == "stretch":
        return frame.resize(target_size, resample=resample_filter)

    img_ratio = frame.width / frame.height
    target_ratio = w_target / h_target

    if (fit_mode == "fit" and img_ratio > target_ratio) or (
        fit_mode == "fill" and img_ratio < target_ratio
    ):
        scale_h = max(1, int(w_target / img_ratio))
        scaled_img = frame.resize((w_target, scale_h), resample=resample_filter)
    else:
        scale_w = max(1, int(h_target * img_ratio))
        scaled_img = frame.resize((scale_w, h_target), resample=resample_filter)

    new_frame = Image.new("RGB", target_size, letterbox_color)
    paste_x = (w_target - scaled_img.width) // 2
    paste_y = (h_target - scaled_img.height) // 2
    new_frame.paste(scaled_img, (paste_x, paste_y))
    return new_frame
