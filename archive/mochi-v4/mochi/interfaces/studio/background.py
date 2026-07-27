"""GradientBackground — the Studio's backdrop layer.

A standalone widget so the look is an *overlay* that can be restyled, animated,
or recoloured later without touching the content. Near-pure black, with the
accent colour bleeding in from the EDGES (bottom corners strongest, fading to
black in the center). Reads its colours from theme.py; sits behind everything
and lets clicks pass through.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from .theme import BASE_RGB, GLOW_PRIMARY, GLOW_SECONDARY


def _glow(base: QColor, alpha: int) -> QColor:
    c = QColor(base)
    c.setAlpha(alpha)
    return c


class GradientBackground(QWidget):
    """Near-black field with the accent glowing in from the bottom edges."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Never intercept input — the content sits on top.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, e: Any) -> None:  # noqa: N802 — Qt override
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        w, h = r.width(), r.height()
        p.fillRect(r, BASE_RGB)  # near-pure black field

        # Primary edge glow — anchored at the bottom-left CORNER, reaching in.
        g1 = QRadialGradient(0.0, float(h), w * 0.7)
        g1.setColorAt(0.0, _glow(GLOW_PRIMARY, 115))
        g1.setColorAt(0.45, _glow(GLOW_PRIMARY, 28))
        g1.setColorAt(1.0, _glow(GLOW_PRIMARY, 0))
        p.fillRect(r, QBrush(g1))

        # Secondary edge glow — bottom-right corner, softer.
        g2 = QRadialGradient(float(w), float(h), w * 0.55)
        g2.setColorAt(0.0, _glow(GLOW_SECONDARY, 50))
        g2.setColorAt(0.6, _glow(GLOW_SECONDARY, 11))
        g2.setColorAt(1.0, _glow(GLOW_SECONDARY, 0))
        p.fillRect(r, QBrush(g2))
        p.end()
