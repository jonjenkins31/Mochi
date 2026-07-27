from __future__ import annotations

from typing import Optional

from .decoders import MediaFrames, decode_gif

from .media_base import DecodedMediaAnimation


class GifHandler(DecodedMediaAnimation):
    """Plays animated GIF/APNG assets."""

    name = "GIF"
    DEFAULT_LOOP = True

    def decode(
        self,
        path: str,
        *,
        target_size: tuple[int, int],
        fit_mode: str,
        letterbox: tuple[int, int, int],
    ) -> Optional[MediaFrames]:
        return decode_gif(
            path,
            target_size=target_size,
            fit_mode=fit_mode,
            letterbox_color=letterbox,
        )
