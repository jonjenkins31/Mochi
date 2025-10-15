from __future__ import annotations

from typing import Optional

from .decoders import MediaFrames, decode_image

from .media_base import DecodedMediaAnimation


class ImageHandler(DecodedMediaAnimation):
    """Displays a single raster image."""

    name = "IMAGE"
    supports_loop = False
    supports_speed = False

    def decode(
        self,
        path: str,
        *,
        target_size: tuple[int, int],
        fit_mode: str,
        letterbox: tuple[int, int, int],
    ) -> Optional[MediaFrames]:
        return decode_image(
            path,
            target_size=target_size,
            fit_mode=fit_mode,
            letterbox_color=letterbox,
        )
