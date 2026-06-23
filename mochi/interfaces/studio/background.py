"""GradientBackground — the Studio's backdrop layer.

A standalone widget so the look is an *overlay* that can be restyled, animated,
or swapped later without touching the content. Primarily black with soft purple
highlights; reads its colours from theme.py. Sits behind everything and lets
clicks pass through to the content on top.
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
    """Near-black field with two soft purple radial highlights."""

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
        p.fillRect(r, BASE_RGB)

        # Primary highlight — top-left.
        g1 = QRadialGradient(w * 0.16, h * 0.04, w * 0.70)
        g1.setColorAt(0.0, _glow(GLOW_PRIMARY, 90))
        g1.setColorAt(1.0, _glow(GLOW_PRIMARY, 0))
        p.fillRect(r, QBrush(g1))

        # Secondary highlight — bottom-right, softer.
        g2 = QRadialGradient(w * 0.94, h * 1.02, w * 0.62)
        g2.setColorAt(0.0, _glow(GLOW_SECONDARY, 55))
        g2.setColorAt(1.0, _glow(GLOW_SECONDARY, 0))
        p.fillRect(r, QBrush(g2))
        p.end()
