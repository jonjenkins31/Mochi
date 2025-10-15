# animations/media_handler.py

"""Generic handler that picks the appropriate media decoder based on file type."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .decoders import MediaFrames, decode_gif, decode_image, decode_video

from .media_base import DecodedMediaAnimation

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
ANIMATED_EXTENSIONS = {".gif", ".apng"}


class MediaHandler(DecodedMediaAnimation):
    """
    Backwards-compatible handler for the legacy 'MEDIA' command.

    Delegates to the specific decoder based on the asset extension.
    """

    name = "MEDIA"
    DEFAULT_LOOP = True

    def decode(
        self,
        path: str,
        *,
        target_size: tuple[int, int],
        fit_mode: str,
        letterbox: tuple[int, int, int],
    ) -> Optional[MediaFrames]:
        suffix = Path(path).suffix.lower()

        if suffix in VIDEO_EXTENSIONS:
            return decode_video(
                path,
                target_size=target_size,
                fit_mode=fit_mode,
                letterbox_color=letterbox,
            )

        if suffix in ANIMATED_EXTENSIONS:
            return decode_gif(
                path,
                target_size=target_size,
                fit_mode=fit_mode,
                letterbox_color=letterbox,
            )

        return decode_image(
            path,
            target_size=target_size,
            fit_mode=fit_mode,
            letterbox_color=letterbox,
        )
