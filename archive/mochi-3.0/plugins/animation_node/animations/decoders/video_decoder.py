from __future__ import annotations

import logging
from typing import Optional, Tuple

from PIL import Image

from .base import MediaFrames, resize_frame

logger = logging.getLogger(__name__)

try:
    from moviepy.editor import VideoFileClip

    MOVIEPY_AVAILABLE = True
    _MOVIEPY_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency optional
    VideoFileClip = None  # type: ignore[assignment]
    MOVIEPY_AVAILABLE = False
    _MOVIEPY_IMPORT_ERROR = exc

try:
    import imageio.v3 as imageio_v3

    IMAGEIO_AVAILABLE = True
    _IMAGEIO_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - dependency optional
    imageio_v3 = None  # type: ignore[assignment]
    IMAGEIO_AVAILABLE = False
    _IMAGEIO_IMPORT_ERROR = exc

try:
    import imageio_ffmpeg  # noqa: F401  # Ensure ffmpeg plugin is registered

    _IMAGEIO_FFMPEG_AVAILABLE = True
    _IMAGEIO_FFMPEG_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - optional helper
    _IMAGEIO_FFMPEG_AVAILABLE = False
    _IMAGEIO_FFMPEG_ERROR = exc


def decode_video(
    path: str,
    target_size: Tuple[int, int],
    fit_mode: str = "fit",
    letterbox_color: Tuple[int, int, int] = (0, 0, 0),
) -> Optional[MediaFrames]:
    """Decodes a video file into frames using moviepy or imageio."""
    if MOVIEPY_AVAILABLE:
        result = _decode_with_moviepy(
            path,
            target_size=target_size,
            fit_mode=fit_mode,
            letterbox_color=letterbox_color,
        )
        if result:
            return result
        logger.warning("Falling back to imageio decoder after moviepy failure for %s", path)

    if IMAGEIO_AVAILABLE:
        return _decode_with_imageio(
            path,
            target_size=target_size,
            fit_mode=fit_mode,
            letterbox_color=letterbox_color,
        )

    msg_parts = []
    if _MOVIEPY_IMPORT_ERROR is not None:
        msg_parts.append(f"moviepy: {_MOVIEPY_IMPORT_ERROR}")
    if _IMAGEIO_IMPORT_ERROR is not None:
        msg_parts.append(f"imageio.v3: {_IMAGEIO_IMPORT_ERROR}")
    if not _IMAGEIO_FFMPEG_AVAILABLE and _IMAGEIO_FFMPEG_ERROR is not None:
        msg_parts.append(f"imageio-ffmpeg: {_IMAGEIO_FFMPEG_ERROR}")
    logger.error(
        "No supported video decoder is available. Install moviepy or imageio-ffmpeg. (%s)",
        "; ".join(msg_parts) if msg_parts else "missing dependencies",
    )
    return None


def _decode_with_moviepy(
    path: str,
    *,
    target_size: Tuple[int, int],
    fit_mode: str,
    letterbox_color: Tuple[int, int, int],
) -> Optional[MediaFrames]:
    if not MOVIEPY_AVAILABLE or VideoFileClip is None:  # pragma: no cover - guard
        return None

    try:
        clip = VideoFileClip(  # type: ignore[misc]
            path,
            audio=False,
            target_resolution=(target_size[1], target_size[0]),
        )
    except Exception as exc:
        logger.error("Failed to open video file with moviepy: %s (%s)", path, exc)
        return None

    fps = clip.fps or 24
    frame_duration_ms = max(1, int(round(1000 / fps)))

    frames = []
    durations = []

    try:
        for frame_np in clip.iter_frames(dtype="uint8"):
            frame = Image.fromarray(frame_np)
            frame_resized = resize_frame(frame, target_size, fit_mode, letterbox_color)
            frames.append(frame_resized)
            durations.append(frame_duration_ms)
    except Exception as exc:
        logger.error("Error decoding video frames for %s with moviepy: %s", path, exc)
        clip.close()
        return None
    finally:
        clip.close()

    if not frames:
        logger.warning("No frames decoded from video %s using moviepy", path)
        return None

    logger.info("Decoded %d video frames from %s at %.2f FPS (moviepy)", len(frames), path, fps)
    return MediaFrames(frames, durations)


def _decode_with_imageio(
    path: str,
    *,
    target_size: Tuple[int, int],
    fit_mode: str,
    letterbox_color: Tuple[int, int, int],
) -> Optional[MediaFrames]:
    if not IMAGEIO_AVAILABLE or imageio_v3 is None:  # pragma: no cover - guard
        return None

    plugin_name: str | None = "FFMPEG"
    metadata = {}
    try:
        metadata = imageio_v3.immeta(path, plugin=plugin_name)
    except Exception as exc:
        logger.warning(
            "ImageIO FFMPEG plugin unavailable while reading metadata for %s: %s. Retrying with auto plugin.",
            path,
            exc,
        )
        plugin_name = None
        try:
            metadata = imageio_v3.immeta(path)
        except Exception as exc2:
            logger.error("Failed to read metadata for video %s: %s", path, exc2)
            metadata = {}

    fps = metadata.get("fps") or metadata.get("framerate") or metadata.get("video", {}).get("fps")
    if isinstance(fps, (tuple, list)) and fps:
        try:
            fps = fps[0] / fps[1]
        except Exception:  # pragma: no cover - defensive
            fps = None

    try:
        fps_value = float(fps)
    except (TypeError, ValueError):
        fps_value = 24.0

    frame_duration_ms = max(1, int(round(1000 / fps_value)))

    frames = []
    durations = []

    try:
        if plugin_name:
            frame_iter = imageio_v3.imiter(path, plugin=plugin_name)
        else:
            frame_iter = imageio_v3.imiter(path)

        for frame_np in frame_iter:
            frame = Image.fromarray(frame_np)
            frame_resized = resize_frame(frame, target_size, fit_mode, letterbox_color)
            frames.append(frame_resized)
            durations.append(frame_duration_ms)
    except Exception as exc:
        logger.error("Error decoding video frames for %s with imageio: %s", path, exc)
        return None

    if not frames:
        logger.warning("No frames decoded from video %s using imageio", path)
        return None

    logger.info(
        "Decoded %d video frames from %s at %.2f FPS using imageio (plugin=%s)",
        len(frames),
        path,
        fps_value,
        plugin_name or "auto",
    )
    return MediaFrames(frames, durations)
