from __future__ import annotations

from typing import Optional

from .decoders import MediaFrames, decode_video

from .media_base import DecodedMediaAnimation


class VideoHandler(DecodedMediaAnimation):
    """Plays video assets using moviepy."""

    name = "VIDEO"
    DEFAULT_LOOP = False

    def decode(
        self,
        path: str,
        *,
        target_size: tuple[int, int],
        fit_mode: str,
        letterbox: tuple[int, int, int],
    ) -> Optional[MediaFrames]:
        return decode_video(
            path,
            target_size=target_size,
            fit_mode=fit_mode,
            letterbox_color=letterbox,
        )
