"""SVG line icons for the Studio sidebar + the Mochi logo.

Monochrome Feather-style strokes, tinted + rasterised on demand so the same
glyph serves both the dim (inactive) and bright (active) nav states. One place
to swap the whole icon set.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_WRAP = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
    'stroke-linejoin="round">{}</svg>'
)

# Feather/Lucide-style paths, keyed by nav id.
_PATHS = {
    "dashboard": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h14V9.5"/>',
    "characters": '<circle cx="12" cy="8" r="3.4"/><path d="M5 20c0-3.5 3-5.6 7-5.6s7 2.1 7 5.6"/>',
    "animation": '<path d="M12 3l1.7 4.8L18.5 9l-4.8 1.2L12 15l-1.7-4.8L5.5 9l4.8-1.2z"/>',
    "editors": '<path d="M12 20h9"/><path d="M16.5 3.5a2 2 0 0 1 2.8 2.8L7 18.5 3 19.5l1-4z"/>',
    "media": '<rect x="3" y="5" width="18" height="13" rx="2"/><path d="M10.5 9l4.5 2.5-4.5 2.5z"/>',
    "assets": ('<rect x="3.5" y="3.5" width="7" height="7" rx="1.2"/>'
               '<rect x="13.5" y="3.5" width="7" height="7" rx="1.2"/>'
               '<rect x="3.5" y="13.5" width="7" height="7" rx="1.2"/>'
               '<rect x="13.5" y="13.5" width="7" height="7" rx="1.2"/>'),
    "packs": ('<path d="M12 3l8.5 4.5L12 12 3.5 7.5z"/>'
              '<path d="M3.5 12 12 16.5 20.5 12"/><path d="M3.5 16.5 12 21l8.5-4.5"/>'),
    "chat": '<path d="M20 14a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z"/>',
    "diagnostics": '<path d="M3 12h4l2.5-7 4 14L16 12h5"/>',
    "learn": '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15.5H6.5A2.5 2.5 0 0 0 4 21z"/><path d="M4 5.5V21"/>',
    "settings": ('<circle cx="12" cy="12" r="3"/>'
                 '<path d="M19.4 13a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.2a1.7 1.7 0 0 0-2.9-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 4.6 14H4a2 2 0 1 1 0-4h.2a1.7 1.7 0 0 0 1.1-2.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 2.9-1.1V3a2 2 0 1 1 4 0v.2a1.7 1.7 0 0 0 2.9 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.4 1.9z"/>'),
}

# The Mochi logo — a faceted hexagon gem (dark fill, accent facets).
_LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'stroke-linejoin="round">'
    '<path d="M12 2 20.7 7 20.7 17 12 22 3.3 17 3.3 7Z" fill="{fill}" '
    'stroke="{stroke}" stroke-width="1.3"/>'
    '<path d="M12 2 12 12M20.7 7 12 12M20.7 17 12 12M12 22 12 12M3.3 17 12 12M3.3 7 12 12" '
    'fill="none" stroke="{stroke}" stroke-width="0.7" opacity="0.5"/></svg>'
)


def _render(svg: str, size: int) -> QPixmap:
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def icon(name: str, color: str, size: int = 18) -> QIcon:
    """A nav icon, stroked in ``color``."""
    svg = _WRAP.format(_PATHS[name]).replace("currentColor", color)
    return QIcon(_render(svg, size))


def logo_pixmap(fill: str, stroke: str, size: int = 24) -> QPixmap:
    """The faceted Mochi gem."""
    return _render(_LOGO.format(fill=fill, stroke=stroke), size)
