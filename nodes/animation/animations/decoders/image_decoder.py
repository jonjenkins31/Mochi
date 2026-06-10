from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image

from .base import MediaFrames, ensure_rgb, resize_frame, logger


def decode_image(
    path: str,
    target_size: Tuple[int, int],
    fit_mode: str = "fit",
    letterbox_color: Tuple[int, int, int] = (0, 0, 0),
) -> Optional[MediaFrames]:
    """Decodes a static raster image into a single frame."""
    try:
        img = Image.open(path)
    except Exception as exc:
        logger.error("Failed to open image file: %s (%s)", path, exc)
        return None

    try:
        frame = resize_frame(ensure_rgb(img.copy()), target_size, fit_mode, letterbox_color)
    except Exception as exc:
        logger.error("Failed to process image %s: %s", path, exc)
        return None
    finally:
        img.close()

    logger.info("Decoded image frame from %s", path)
    return MediaFrames([frame], [0])
