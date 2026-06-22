"""Shared brand-asset helpers for the GUI surfaces.

Sits beside :mod:`tray`, :mod:`chat_window`, :mod:`studio_window` so
each can pull the Lilith disc icon without importing the tray module
(which would otherwise drag ``pynput`` and the global hotkey listener
into every mode that shows a window).

The module ships a single function — :func:`lilith_brand_icon` —
that returns a :class:`PyQt6.QtGui.QIcon` for the bundled
``src/lilith/assets/lilith_icon.png``. Falls back to the space-invader
emoji rendered into a 64×64 pixmap when the asset is missing or
unreadable, so a stripped-down wheel install never boots blank.
"""

from __future__ import annotations

import logging
import pathlib

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap


logger = logging.getLogger(__name__)


_ASSETS_DIR = pathlib.Path(__file__).resolve().parents[1] / "assets"
_FALLBACK_EMOJI = "👾"


def _emoji_icon(emoji_text: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setFont(QFont("Apple Color Emoji", 48))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, emoji_text)
    painter.end()
    return QIcon(pixmap)


def lilith_brand_icon() -> QIcon:
    """The Lilith disc logo, loaded from the bundled assets directory.

    Falls back to the space-invader emoji with a warning log if the
    asset is missing or unreadable, so the tray / pill / chat / studio
    surfaces never boot blank if the wheel was packaged without
    ``assets/`` for some reason.
    """
    path = _ASSETS_DIR / "lilith_icon.png"
    if path.is_file():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
        logger.warning("brand icon at %s is unreadable; falling back to emoji", path)
    else:
        logger.warning("brand icon asset missing at %s; falling back to emoji", path)
    return _emoji_icon(_FALLBACK_EMOJI)
