"""Mochi Studio design tokens + stylesheet — the single source of styling.

Industry-standard split: every colour, the label helper, the gradient-backdrop
tokens, and the full QSS live here, so window.py / sidebar.py / the pages stay
pure structure. Restyle the whole app from this one file.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QLabel

# ── palette ─────────────────────────────────────────────────────────
DEEP = "#0B0910"        # near-black base
BG = "#151221"
PANEL = "#1C1830"
PANEL_HI = "#262038"
STROKE = "#2C2545"
ACCENT = "#7C5CFF"
ACCENT_HI = "#9B7DFF"
INK = "#ECEAF6"
INK_DIM = "#8A85A6"
GOOD = "#4ADE80"

# ── gradient-backdrop tokens (background.GradientBackground paints these) ──
BASE_RGB = QColor(11, 9, 16)            # the near-black field
GLOW_PRIMARY = QColor(124, 92, 255)     # the main purple highlight (top-left)
GLOW_SECONDARY = QColor(150, 110, 255)  # a softer second highlight (bottom-right)

# Translucent surface fills, so the backdrop's purple glow shows THROUGH the
# panels (the "overlay" look the operator asked for — adjustable from here).
SIDEBAR_FILL = "rgba(20, 17, 32, 0.62)"
PANEL_FILL = "rgba(28, 24, 48, 0.66)"
BAR_FILL = "rgba(19, 16, 30, 0.50)"


def _label(text: str, *, color: str = INK, size: int = 13, bold: bool = False) -> QLabel:
    lab = QLabel(text)
    f = QFont("SF Pro Text", size)
    f.setBold(bold)
    lab.setFont(f)
    lab.setStyleSheet(f"color: {color}; background: transparent;")
    return lab


def stylesheet() -> str:
    """The full Studio QSS. Panels are translucent over the gradient backdrop."""
    return f"""
        QWidget#MochiStudio {{ background: transparent; }}
        QFrame#Sidebar {{ background: {SIDEBAR_FILL}; border-right: 1px solid {STROKE}; }}
        QPushButton#NavItem {{
            text-align: left; padding: 11px 12px; border: none;
            border-radius: 10px; color: {INK_DIM};
            font-size: 13px; background: transparent;
        }}
        QPushButton#NavItem:hover {{ background: {PANEL_HI}; color: {INK}; }}
        QPushButton#NavItem:checked {{ background: {ACCENT}; color: white; }}

        QFrame#ProfileCard {{
            background: {PANEL_FILL}; border: 1px solid {STROKE}; border-radius: 14px;
        }}
        QLabel#ProfileAvatar {{
            background: {PANEL_HI}; color: {INK}; border-radius: 18px;
            font-weight: 700; border: 1px solid {STROKE};
        }}

        QFrame#AddonCard {{
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 {ACCENT}, stop:1 #5B3FD6);
            border-radius: 14px;
        }}
        QPushButton#AddonBtn {{
            background: rgba(255,255,255,0.18); color: white; border: none;
            border-radius: 9px; padding: 8px; font-weight: 600;
        }}
        QPushButton#AddonBtn:hover {{ background: rgba(255,255,255,0.30); }}

        QFrame#TopBar {{ background: {BAR_FILL}; border-bottom: 1px solid {STROKE}; }}
        QPushButton#Tab {{
            border: none; padding: 8px 16px; border-radius: 9px;
            color: {INK_DIM}; font-size: 13px; background: transparent;
        }}
        QPushButton#Tab:checked {{ background: {PANEL_HI}; color: {INK}; }}
        QLineEdit#Search {{
            background: {PANEL}; border: 1px solid {STROKE}; border-radius: 9px;
            padding: 7px 12px; color: {INK}; font-size: 12px;
        }}
        QLineEdit#Search:focus {{ border: 1px solid {ACCENT}; }}
        QPushButton#Accent {{
            background: {ACCENT}; color: white; border: none;
            border-radius: 9px; padding: 8px 18px; font-weight: 600;
        }}
        QPushButton#Accent:hover {{ background: {ACCENT_HI}; }}
        QLabel#Avatar {{
            background: {PANEL_HI}; color: {INK}; border-radius: 17px;
            font-weight: 700; border: 1px solid {STROKE};
        }}
        QFrame#Stage {{
            background: qlineargradient(x1:0,y1:0,x2:0.6,y2:1,
                stop:0 {PANEL_HI}, stop:1 {DEEP});
            border-radius: 18px; border: 1px solid {STROKE};
        }}
        QLabel#CharView {{ color: {INK_DIM}; font-size: 40px; }}
        QFrame#RightPanel {{ background: {PANEL_FILL}; border-radius: 16px; border: 1px solid {STROKE}; }}
        QFrame#BottomBar {{ background: {BAR_FILL}; border-top: 1px solid {STROKE}; }}
        QFrame#Thumb {{ background: {PANEL_HI}; border-radius: 10px; border: 1px solid {STROKE}; }}
        QListWidget#Library {{
            background: {PANEL}; border: 1px solid {STROKE}; border-radius: 12px;
            color: {INK}; font-size: 12px; padding: 6px; outline: none;
        }}
        QListWidget#Library::item {{ padding: 7px 8px; border-radius: 7px; }}
        QListWidget#Library::item:selected {{ background: {ACCENT}; color: white; }}
        QListWidget#Library::item:hover {{ background: {PANEL_HI}; }}
        QSlider::groove:horizontal {{ height: 4px; background: {STROKE}; border-radius: 2px; }}
        QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
        QSlider::handle:horizontal {{
            background: white; width: 13px; height: 13px;
            margin: -5px 0; border-radius: 7px;
        }}
    """
