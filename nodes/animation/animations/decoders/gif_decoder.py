from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image, ImageSequence

from .base import MediaFrames, ensure_rgb, resize_frame, logger


def decode_gif(
    path: str,
    target_size: Tuple[int, int],
    fit_mode: str = "fit",
    letterbox_color: Tuple[int, int, int] = (0, 0, 0),
) -> Optional[MediaFrames]:
    """Decodes an animated GIF/APNG into frames."""
    try:
        img = Image.open(path)
    except Exception as exc:
        logger.error("Failed to open animated image: %s (%s)", path, exc)
        return None

    frames = []
    durations = []

    try:
        for frame in ImageSequence.Iterator(img):
            frame_rgb = ensure_rgb(frame.copy())
            frame_resized = resize_frame(frame_rgb, target_size, fit_mode, letterbox_color)
            frames.append(frame_resized)
            durations.append(int(frame.info.get("duration", 100)))
    except Exception as exc:
        logger.error("Error processing frames for %s: %s", path, exc)
        frames.clear()
    finally:
        img.close()

    if not frames:
        logger.warning("No frames decoded from animated image %s", path)
        return None

    logger.info("Decoded %d GIF frames from %s", len(frames), path)
    return MediaFrames(frames, durations)
