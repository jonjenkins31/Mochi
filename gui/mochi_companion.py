"""Mochi Companion App — operator-first product surface (Phase A.1+A.2).

Wondershare-inspired Qt layout (per OPERATOR_PRODUCT_PLAN.md):

    ┌───────────┬──────────────────────────────────────────────┐
    │ Sidebar   │  Top bar (filter chips + search)             │
    │           ├──────────────────────────────────────────────┤
    │ Home      │                                              │
    │ Library   │  Page content (Library = card grid)          │
    │ Scenes    │                                              │
    │ Triggers  │                                              │
    │ Schedule  │                                              │
    │ Editors   │                                              │
    │ Settings  │                                              │
    └───────────┴──────────────────────────────────────────────┘

Phase A.1 (skeleton): sidebar + page stack + Wondershare-style theme
Phase A.2 (functional): Library page reads CATALOG.json, click → ZMQ

Stub pages (Home, Scenes, Triggers, Schedule, Editors, Settings)
show "coming in Phase B/C" placeholders so the structure is visible
but doesn't pretend to work.

Usage:
    python gui/mochi_companion.py
    python gui/mochi_companion.py --ctrl-addr tcp://127.0.0.1:5556

Reads:
    assets/CATALOG.json   (built by tools/build_catalog.py)
    config.yaml           (broker addresses)

Sends to:
    tcp://127.0.0.1:5556   PUSH — animation node ctrl
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSize, Signal, QTimer, QUrl
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPalette, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QStackedWidget, QListWidget, QListWidgetItem,
    QScrollArea, QSizePolicy, QSpacerItem,
    QTextBrowser, QSplitter, QInputDialog,
)

import zmq

GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
CATALOG_PATH = PROJECT_ROOT / "assets" / "CATALOG.json"
PACKS_DIR    = PROJECT_ROOT / "assets" / "packs"
SKINS_DIR    = PROJECT_ROOT / "assets" / "skins"
THUMBS_DIR   = PROJECT_ROOT / "assets" / "thumbs"
PINNED_FILE  = PROJECT_ROOT / "assets" / "pinned.json"
LEARN_DIR    = PROJECT_ROOT / "docs" / "learn"
MINI_LAUNCHER = GUI_DIR / "mochi_vdisplay_player_qt.py"

# Ordered chapter list (sidebar in the Learn page).  Operator can
# extend by dropping <slug>.md in docs/learn/ and appending the
# (slug, title) tuple here.
LEARN_CHAPTERS: list[tuple[str, str]] = [
    ("index",         "Overview"),
    ("static_images", "01 · Static images"),
    ("bitmaps",       "02 · Bitmaps (1-bit)"),
    ("gifs",          "03 · GIFs"),
    ("sprites",       "04 · Sprite sheets"),
    ("video",         "05 · Video clips"),
    ("math",          "06 · Procedural / math"),
    ("animations",    "07 · Eye animations (JSON)"),
    ("mscripts",      "08 · MochiScript"),
]

DEFAULT_CTRL_ADDR = "tcp://127.0.0.1:5556"
DEFAULT_HEALTH_ADDR = "tcp://127.0.0.1:5555"


# ── Wondershare-inspired theme ─────────────────────────────────────

ACCENT     = "#8b5cf6"   # purple — matches Wondershare brand
ACCENT_BG  = "#f5f3ff"   # very light purple — sidebar hover
ACCENT_DARK = "#7c3aed"  # darker purple — pressed

BG_BASE    = "#fafafa"
BG_CARD    = "#ffffff"
BG_SIDEBAR = "#fafafa"

TEXT_MAIN  = "#1f2937"
TEXT_MUTED = "#6b7280"
TEXT_TAG   = "#4b5563"

BORDER     = "#e5e7eb"
BORDER_HOVER = "#d1d5db"

BADGE_COLORS = {
    "happy":      ("#fef3c7", "#92400e"),
    "sad":        ("#dbeafe", "#1e40af"),
    "angry":      ("#fee2e2", "#991b1b"),
    "love":       ("#fce7f3", "#9d174d"),
    "surprised":  ("#ede9fe", "#5b21b6"),
    "thinking":   ("#e0e7ff", "#3730a3"),
    "focused":    ("#cffafe", "#155e75"),
    "curious":    ("#d1fae5", "#065f46"),
    "sleepy":     ("#e0e7ff", "#312e81"),
    "scared":     ("#fee2e2", "#7f1d1d"),
    "energetic":  ("#ffedd5", "#9a3412"),
    "defensive":  ("#f3f4f6", "#374151"),
    "neutral":    ("#f3f4f6", "#374151"),
}


STYLESHEET = f"""
QMainWindow, QWidget {{
    background: {BG_BASE};
    color: {TEXT_MAIN};
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}}

/* Sidebar */
#sidebar {{
    background: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
}}
#sidebar_logo {{
    color: {ACCENT};
    font-size: 18px;
    font-weight: 700;
    padding: 18px 20px 24px 20px;
}}
#sidebar_section_label {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 16px 20px 6px 20px;
}}
/* Sidebar nav items — full-width selection state matches
   Wondershare's "selected fills the whole row" treatment. */
QPushButton.sidebar_btn {{
    background: transparent;
    color: {TEXT_MAIN};
    text-align: left;
    padding: 12px 20px;
    border: none;
    border-radius: 0;
    margin: 0;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton.sidebar_btn:hover {{
    background: rgba(139, 92, 246, 0.06);
}}
QPushButton.sidebar_btn:checked {{
    background: {ACCENT_BG};
    color: {ACCENT_DARK};
    font-weight: 600;
    border-left: 3px solid {ACCENT_DARK};
    padding-left: 17px;
}}

/* Top bar */
#topbar {{
    background: {BG_BASE};
    border-bottom: 1px solid {BORDER};
}}
#page_title {{
    font-size: 28px;
    font-weight: 700;
    color: {TEXT_MAIN};
    padding-bottom: 4px;
}}

QPushButton.tab_btn {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
    padding: 12px 18px 14px 18px;
    margin-right: 2px;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton.tab_btn:hover {{
    color: {TEXT_MAIN};
}}
QPushButton.tab_btn:checked {{
    color: {ACCENT_DARK};
    border-bottom: 3px solid {ACCENT_DARK};
    font-weight: 700;
    padding-bottom: 11px;
}}

QLineEdit#search {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    min-width: 280px;
}}
QLineEdit#search:focus {{
    border-color: {ACCENT};
}}

/* Card grid */
#scrollarea {{
    background: {BG_BASE};
    border: none;
}}
QFrame.card {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame.card:hover {{
    border-color: {ACCENT};
}}
QLabel.card_title {{
    color: {TEXT_MAIN};
    font-size: 14px;
    font-weight: 600;
    padding: 4px 0 0 0;
}}
QLabel.card_subtitle {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel.card_preview {{
    background: {BG_BASE};
    color: {TEXT_MUTED};
    border-radius: 6px;
    font-size: 32px;
    font-weight: 700;
    padding: 30px 0;
}}

/* Stub-page placeholder */
QLabel.coming_soon {{
    color: {TEXT_MUTED};
    font-size: 14px;
}}
QLabel.coming_soon_heading {{
    color: {TEXT_MAIN};
    font-size: 18px;
    font-weight: 600;
}}
"""


# ── ZMQ bridge ─────────────────────────────────────────────────────

class CtrlBridge:
    """PUSH socket to the animation node's ctrl endpoint.

    Matches the pattern in gui/mochi_gui.py so commands behave
    identically.  Connects lazily; failures don't crash the GUI.
    """

    def __init__(self, ctrl_addr: str, logger: logging.Logger) -> None:
        self.ctrl_addr = ctrl_addr
        self.logger = logger
        self._ctx = zmq.Context.instance()
        self._push: zmq.Socket | None = None
        try:
            self._push = self._ctx.socket(zmq.PUSH)
            self._push.setsockopt(zmq.LINGER, 0)
            self._push.connect(ctrl_addr)
            self.logger.info("ctrl connected — %s", ctrl_addr)
        except zmq.ZMQError as exc:
            self.logger.error("ctrl connect failed: %s", exc)
            self._push = None

    def send(self, command: str) -> None:
        if self._push is None:
            self.logger.warning(
                "no ctrl socket — would have sent: %s", command,
            )
            return
        try:
            self._push.send_string(command)
            self.logger.info("ctrl send: %s", command)
        except zmq.ZMQError as exc:
            self.logger.error("ctrl send failed: %s — %s", command, exc)


# ── catalog loader ─────────────────────────────────────────────────

def load_catalog() -> dict:
    if not CATALOG_PATH.is_file():
        return {"entries": []}
    try:
        return json.loads(CATALOG_PATH.read_text())
    except Exception:  # noqa: BLE001
        return {"entries": []}


def discover_skins() -> list[dict]:
    """Walk assets/skins/<id>/meta.yaml + body.png and return one
    summary dict per skin.  See docs/SKIN_CONVENTION.md.

    A skin without a meta.yaml is skipped silently.  A meta.yaml
    without a sibling body.png logs to the manifest's ``_warning``
    field so the operator sees it in the picker.
    """
    if not SKINS_DIR.is_dir():
        return []
    try:
        import yaml
    except ImportError:
        return []
    skins: list[dict] = []
    for child in sorted(SKINS_DIR.iterdir()):
        if not child.is_dir():
            continue
        manifest = child / "meta.yaml"
        body = child / "body.png"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text()) or {}
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        data["_path"] = str(child)
        data["_body_path"] = str(body)
        data.setdefault("id", child.name)
        data.setdefault("name", child.name)
        if not body.is_file():
            data["_warning"] = "body.png missing"
        skins.append(data)
    return skins


def launch_mini_window(
    skin_path: Path | None,
    logger: logging.Logger,
) -> subprocess.Popen | None:
    """Spawn the frameless Qt overlay (mochi_vdisplay_player_qt.py)
    as a subprocess so the companion stays interactive.

    When ``skin_path`` is provided, we use its ``body.png``; the
    launcher's existing --image flag is the bridge.  ``meta.yaml``'s
    ``screen_bbox`` etc. aren't wired into the launcher CLI today —
    follow-up commit adds --skin to the launcher so it reads the
    whole meta in one go.  For now the existing ``--profile`` flag
    + config.yaml ``display_players`` block continues to handle the
    detailed settings until the launcher is updated.
    """
    if not MINI_LAUNCHER.is_file():
        logger.warning("mini launcher missing: %s", MINI_LAUNCHER)
        return None
    cmd: list[str] = [sys.executable, str(MINI_LAUNCHER)]
    if skin_path is not None:
        body = skin_path / "body.png"
        if body.is_file():
            cmd.extend(["--image", str(body)])
    try:
        proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))
        logger.info("launched mini window — pid=%d cmd=%s",
                    proc.pid, " ".join(cmd))
        return proc
    except Exception as exc:  # noqa: BLE001
        logger.error("mini launch failed: %s", exc)
        return None


def discover_packs() -> list[dict]:
    """Walk assets/packs/<id>/pack.yaml and return one summary dict
    per pack.  Empty list when no packs are authored yet — operator
    is working on them; the surface is ready when they land.

    See docs/PACK_CONVENTION.md for the schema.
    """
    if not PACKS_DIR.is_dir():
        return []
    try:
        import yaml  # local import — yaml is in requirements
    except ImportError:
        return []
    packs: list[dict] = []
    for child in sorted(PACKS_DIR.iterdir()):
        if not child.is_dir():
            continue
        manifest = child / "pack.yaml"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text()) or {}
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        data["_path"] = str(child)
        data.setdefault("id", child.name)
        data.setdefault("name", child.name)
        data.setdefault("slots", {})
        packs.append(data)
    return packs


# ── widgets ────────────────────────────────────────────────────────

def make_badge(mood: str) -> QLabel:
    bg, fg = BADGE_COLORS.get(mood, BADGE_COLORS["neutral"])
    label = QLabel(mood.upper())
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet(f"""
        background: {bg};
        color: {fg};
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.04em;
        min-width: 60px;
        max-width: 90px;
    """)
    return label


def _thumb_path(entry: dict) -> Path:
    """Resolve the cached thumbnail path for ``entry`` —
    ``assets/thumbs/<sanitised_name>.png``.  Matches the convention
    tools/build_thumbnails.py uses."""
    safe = entry["name"].replace("/", "_").replace(" ", "_")
    return THUMBS_DIR / f"{safe}.png"


def _make_pill_badge(text: str, fg: str, bg: str) -> QLabel:
    """Wondershare-style pill badge (NEW / AI / 4K / etc.)."""
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet(f"""
        background: {bg};
        color: {fg};
        border-radius: 4px;
        padding: 2px 7px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.05em;
    """)
    return label


def _card_badges_for(entry: dict) -> list[QLabel]:
    """Decide which Wondershare-style pill badges a card gets,
    based on the catalog/sidecar fields.  Returns a list of QLabels
    so the caller can lay them out horizontally."""
    badges: list[QLabel] = []
    type_ = entry.get("type", "")
    name = entry.get("name", "").lower()

    # MOCHI badge — Mochi-themed video splits / mochi-named clips
    if "mochi" in name or "mochi" in entry.get("path", "").lower():
        badges.append(_make_pill_badge(
            "MOCHI", "white", ACCENT_DARK,
        ))
    # AI badge — when the asset was an LLM-generated piece (heuristic
    # via the operator's notes field someday; placeholder today)
    if entry.get("ai_generated") is True:
        badges.append(_make_pill_badge(
            "AI", "white",
            "qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {ACCENT_DARK}, stop:1 #ec4899)",
        ))
    # NEW badge — sidecars curated this session (when curated
    # flag becomes a real signal)
    if entry.get("nsfw") is True:
        badges.append(_make_pill_badge(
            "NSFW", "white", "#dc2626",
        ))
    # PACK badge — entry belongs to a pack (future signal once
    # build_catalog merges PACKS.json)
    if entry.get("pack"):
        badges.append(_make_pill_badge(
            "PACK", "white", "#0891b2",
        ))
    return badges


def make_card(entry: dict, on_click) -> QFrame:
    """One catalog entry as a clickable card.  Shows the cached
    thumbnail when present (built by tools/build_thumbnails.py),
    falls back to a first-letter placeholder otherwise.

    Card layout matches the Wondershare reference:
      - Large preview image (75% of card height)
      - Title row (with optional pill badges)
      - Subtitle row (mood badge + type label)
    """
    card = QFrame()
    card.setObjectName("card")
    card.setProperty("class", "card")
    card.setCursor(Qt.PointingHandCursor)
    card.setFixedSize(240, 240)
    card.mousePressEvent = lambda _e: on_click(entry)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 12, 12, 14)
    layout.setSpacing(8)

    # ── Preview tile (bumped to fill most of the card) ────────────
    thumb = _thumb_path(entry)
    preview = QLabel()
    preview.setAlignment(Qt.AlignCenter)
    preview.setFixedHeight(140)
    if thumb.is_file():
        pix = QPixmap(str(thumb))
        if not pix.isNull():
            pix = pix.scaled(
                140, 140,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            preview.setPixmap(pix)
            preview.setStyleSheet(f"""
                background: {BG_BASE};
                border-radius: 8px;
            """)
        else:
            preview.setText(entry["name"][:1].upper())
            preview.setStyleSheet(f"""
                background: {ACCENT_BG};
                color: {ACCENT_DARK};
                border-radius: 8px;
                font-size: 48px;
                font-weight: 700;
            """)
    else:
        preview.setText(entry["name"][:1].upper())
        preview.setStyleSheet(f"""
            background: {ACCENT_BG};
            color: {ACCENT_DARK};
            border-radius: 8px;
            font-size: 48px;
            font-weight: 700;
        """)
    layout.addWidget(preview)

    # Title row: name + any Wondershare-style pill badges inline
    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(6)
    title = QLabel(entry["name"])
    title.setProperty("class", "card_title")
    title.setStyleSheet(
        f"color: {TEXT_MAIN}; font-size: 14px; font-weight: 700;"
    )
    title.setWordWrap(True)
    title_row.addWidget(title, 1)
    for b in _card_badges_for(entry):
        title_row.addWidget(b)
    layout.addLayout(title_row)

    bottom = QHBoxLayout()
    bottom.setContentsMargins(0, 0, 0, 0)
    badge = make_badge(entry.get("mood", "neutral"))
    bottom.addWidget(badge)
    bottom.addStretch()
    type_label = QLabel(entry.get("type", "?"))
    type_label.setStyleSheet(
        f"color: {TEXT_MUTED}; font-size: 11px;"
    )
    bottom.addWidget(type_label)
    layout.addLayout(bottom)

    return card


# ── pages ──────────────────────────────────────────────────────────

class LibraryPage(QWidget):
    """The headline Phase-A.2 page: card grid of every catalog entry,
    with mood/type filter + search.  Click a card → mode <name>."""

    def __init__(self, ctrl: CtrlBridge, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ctrl = ctrl
        self.catalog = load_catalog()
        self.entries = self.catalog.get("entries", [])
        self._current_mood = "all"
        self._current_type = "all"
        self._current_curation = "all"   # all | curated | uncurated
        self._search_text = ""
        # (note: _current_type initialised here is consumed by
        # _filtered() once the Type filter row + _select_type are in
        # place — see __init__ below)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── top bar (page title + search) ─────────────────────────
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(28, 22, 28, 16)
        title = QLabel("Library")
        title.setObjectName("page_title")
        topbar_layout.addWidget(title)
        topbar_layout.addStretch()
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Search animations…")
        self.search.textChanged.connect(self._on_search)
        topbar_layout.addWidget(self.search)
        outer.addWidget(topbar)

        # ── filter chips (mood + type) ────────────────────────────
        # Two dimensions filter the grid with AND logic.  Each row is
        # a labelled chip group with its own "ALL" reset chip.
        # Useful for product browsing AND as a teaching surface: when
        # the operator is explaining "how sprites work" they can hide
        # everything else by clicking TYPE: SPRITES.  Operator note
        # 2026-06-10: "tabs or filters for animation style, like gifs,
        # sprites, etc... different categories... also for education
        # when I teach people about animation".
        moods = ["all"] + sorted(
            {e.get("mood", "neutral") for e in self.entries}
        )
        types = ["all"] + sorted(
            {e.get("type", "?") for e in self.entries}
        )

        self._mood_buttons: dict[str, QPushButton] = {}
        self._type_buttons: dict[str, QPushButton] = {}
        self._curation_buttons: dict[str, QPushButton] = {}

        outer.addWidget(self._build_filter_row(
            "Mood", moods, self._mood_buttons, self._select_mood,
        ))
        outer.addWidget(self._build_filter_row(
            "Type", types, self._type_buttons, self._select_type,
        ))
        # Curation chip row — operator uses to find what still needs
        # a hand-edit on its sidecar.  "Curated" means the operator
        # has touched the sidecar beyond the auto-scaffolded stub;
        # heuristic: any sidecar that has at least one curation field
        # set (we approximate via ``author`` populated, since the
        # scaffolder leaves author commented-out).
        outer.addWidget(self._build_filter_row(
            "Curation",
            ["all", "curated", "uncurated"],
            self._curation_buttons,
            self._select_curation,
            border_bottom=True,
        ))

        # ── card grid (scrollable) ────────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setObjectName("scrollarea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet(f"background: {BG_BASE};")
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(28, 20, 28, 28)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.grid_host)
        outer.addWidget(self.scroll)

        self._rebuild_grid()

    # ── filter-row builder ────────────────────────────────────────

    def _build_filter_row(
        self,
        label: str,
        values: list[str],
        registry: dict[str, QPushButton],
        on_select,
        border_bottom: bool = False,
    ) -> QFrame:
        """One labelled chip row (mood / type).  ``ALL`` resets the
        dimension; rest of the chips form a mutually-exclusive group."""
        row = QFrame()
        bb = (
            f"border-bottom: 1px solid {BORDER};"
            if border_bottom else ""
        )
        row.setStyleSheet(f"background: {BG_BASE}; {bb}")
        h = QHBoxLayout(row)
        h.setContentsMargins(28, 0, 28, 0)
        h.setSpacing(0)
        prefix = QLabel(f"{label.upper()}:")
        prefix.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 0.06em; "
            f"padding-right: 10px;"
        )
        h.addWidget(prefix)
        for v in values:
            btn = QPushButton(v.upper())
            btn.setProperty("class", "tab_btn")
            btn.setCheckable(True)
            if v == "all":
                btn.setChecked(True)
            btn.clicked.connect(
                lambda _checked=False, x=v: on_select(x)
            )
            registry[v] = btn
            h.addWidget(btn)
        h.addStretch()
        return row

    # ── filtering ─────────────────────────────────────────────────

    def _on_search(self, text: str) -> None:
        self._search_text = text.lower().strip()
        self._rebuild_grid()

    def _select_mood(self, mood: str) -> None:
        for m, btn in self._mood_buttons.items():
            btn.setChecked(m == mood)
        self._current_mood = mood
        self._rebuild_grid()

    def _select_type(self, type_: str) -> None:
        for t, btn in self._type_buttons.items():
            btn.setChecked(t == type_)
        self._current_type = type_
        self._rebuild_grid()

    def _select_curation(self, curation: str) -> None:
        for c, btn in self._curation_buttons.items():
            btn.setChecked(c == curation)
        self._current_curation = curation
        self._rebuild_grid()

    @staticmethod
    def _is_curated(entry: dict) -> bool:
        """Heuristic: the sidecar has been hand-touched (operator
        added a curation field).  The scaffolder leaves ``author``
        commented out, so a populated ``author`` is the simplest
        proxy.  Once more reliable curation markers exist, refine."""
        return bool(entry.get("author"))

    def _filtered(self) -> list[dict]:
        results = []
        for e in self.entries:
            if (self._current_mood != "all"
                    and e.get("mood") != self._current_mood):
                continue
            if (self._current_type != "all"
                    and e.get("type") != self._current_type):
                continue
            if self._current_curation == "curated" and not self._is_curated(e):
                continue
            if self._current_curation == "uncurated" and self._is_curated(e):
                continue
            if self._search_text:
                hay = " ".join([
                    e.get("name", ""),
                    e.get("type", ""),
                    " ".join(e.get("tags", [])),
                    e.get("hint", ""),
                ]).lower()
                if self._search_text not in hay:
                    continue
            results.append(e)
        return results

    def _rebuild_grid(self) -> None:
        # Clear existing
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Repopulate
        cols = 4
        for i, entry in enumerate(self._filtered()):
            card = make_card(entry, self._on_card_click)
            r, c = divmod(i, cols)
            self.grid_layout.addWidget(card, r, c)

    def _on_card_click(self, entry: dict) -> None:
        """Click on a card → fire the animation through ctrl socket.

        Also notifies the parent CompanionMain so Home's recent
        strip updates (Phase 3 of the Tk supersede migration).
        """
        name = entry.get("name", "")
        type_ = entry.get("type", "")
        if type_ == "mscripts":
            path = entry.get("path", "")
            self.ctrl.send(f"play {path}")
        else:
            self.ctrl.send(f"node animation mode on {name}")
        # Bubble up to Home so the recent strip updates.  Walk up
        # parents until we find the main window with a HomePage.
        w = self
        while w is not None:
            if hasattr(w, "pages"):
                home = w.pages.get("Home")
                if isinstance(home, HomePage):
                    home.push_recent(name)
                break
            w = w.parent()


class PacksPage(QWidget):
    """Pack browser with stacked card-grid → detail view.

    Empty state when ``assets/packs/`` has no pack.yaml files yet
    (operator: "most stuff are one-offs... I am working on the
    packs").  As packs land, this page populates with pack cards;
    click → slot-by-slot detail view with a Set Active button.

    Active pack persists to ``assets/packs/active.txt`` (single line,
    pack id).  The animation node / LLM picker / reaction button row
    (when wired) read from this file to know which pack to use.

    Signals:
      navigate(label) — request that the main window jump to a
                        different sidebar tab (used by the empty
                        state's "View Library" CTA).
    """

    ACTIVE_FILE = PACKS_DIR / "active.txt"
    navigate = Signal(str)

    def __init__(self, ctrl: CtrlBridge, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ctrl = ctrl
        self._packs = discover_packs()
        self._active_id = self._read_active()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── top bar (with back button — hidden on the grid view) ──
        self._topbar = QFrame()
        self._topbar.setObjectName("topbar")
        tb = QHBoxLayout(self._topbar)
        tb.setContentsMargins(28, 22, 28, 16)
        self._back_btn = QPushButton("← Packs")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {ACCENT_DARK};
                border: none;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ color: {ACCENT}; }}
        """)
        self._back_btn.clicked.connect(self._show_grid)
        self._back_btn.setVisible(False)
        tb.addWidget(self._back_btn)
        self._title = QLabel("Packs")
        self._title.setObjectName("page_title")
        tb.addWidget(self._title)
        tb.addStretch()
        outer.addWidget(self._topbar)

        # ── stacked content ──────────────────────────────────────
        self._stack = QStackedWidget()
        self._grid_page = self._build_grid_page()
        self._stack.addWidget(self._grid_page)
        # Detail page is built on demand per click.
        outer.addWidget(self._stack)

    # ── persistence ───────────────────────────────────────────────

    def _read_active(self) -> str | None:
        try:
            if self.ACTIVE_FILE.is_file():
                txt = self.ACTIVE_FILE.read_text().strip()
                return txt or None
        except Exception:  # noqa: BLE001
            pass
        return None

    def _jump_to_library(self) -> None:
        self.navigate.emit("Library")

    def _write_active(self, pack_id: str) -> None:
        try:
            self.ACTIVE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.ACTIVE_FILE.write_text(pack_id + "\n")
            self._active_id = pack_id
        except Exception as exc:  # noqa: BLE001
            print(f"[packs] failed to persist active.txt: {exc}")

    # ── grid page ────────────────────────────────────────────────

    def _build_grid_page(self) -> QWidget:
        page = QFrame()
        page.setStyleSheet(f"background: {BG_BASE};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(16)

        if not self._packs:
            # Replace bare-text empty state with the Wondershare-style
            # drop-zone card (build_empty_state) — visual consistency
            # with the StubPage emptiness pattern.
            empty = build_empty_state(
                icon_glyph="🎭",
                heading="No packs yet",
                subtitle=(
                    "Browse one-off animations on the <b>Library</b> tab. "
                    "<br><br>"
                    "Drop a pack folder under "
                    "<code>assets/packs/&lt;id&gt;/</code> with a "
                    "<code>pack.yaml</code> manifest and it appears "
                    "here.  See "
                    "<code>docs/PACK_CONVENTION.md</code> for the "
                    "format."
                ),
                cta_label="View Library",
                cta_on_click=self._jump_to_library,
            )
            layout.addWidget(empty)
            return page

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        for i, pack in enumerate(self._packs):
            card = self._make_pack_card(pack)
            r, c = divmod(i, 4)
            grid.addWidget(card, r, c)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def _make_pack_card(self, pack: dict) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setObjectName("card")
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(240, 220)
        card.mousePressEvent = lambda _e, p=pack: self._show_detail(p)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        preview = QLabel(pack.get("name", "")[:1].upper())
        preview.setAlignment(Qt.AlignCenter)
        preview.setStyleSheet(f"""
            background: {ACCENT_BG};
            color: {ACCENT_DARK};
            border-radius: 6px;
            font-size: 44px;
            font-weight: 700;
            min-height: 100px;
        """)
        layout.addWidget(preview)

        # Title row with "Active" badge if this is the chosen pack.
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title = QLabel(pack.get("name", pack.get("id", "?")))
        title.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 14px; font-weight: 600;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        if pack.get("id") == self._active_id:
            badge = QLabel("ACTIVE")
            badge.setStyleSheet(f"""
                background: {ACCENT_DARK};
                color: white;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.05em;
            """)
            title_row.addWidget(badge)
        layout.addLayout(title_row)

        slots = pack.get("slots", {}) or {}
        slot_count = len(slots) if isinstance(slots, dict) else 0
        author = pack.get("author", "")
        meta = QLabel(f"{slot_count} slots  ·  {author}")
        meta.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(meta)

        return card

    # ── detail page ───────────────────────────────────────────────

    def _show_detail(self, pack: dict) -> None:
        """Build + push the slot grid for this pack onto the stack."""
        # Remove any previous detail page so memory doesn't leak.
        while self._stack.count() > 1:
            old = self._stack.widget(1)
            self._stack.removeWidget(old)
            old.deleteLater()

        detail = self._build_detail_page(pack)
        self._stack.addWidget(detail)
        self._stack.setCurrentIndex(1)
        self._title.setText(pack.get("name", pack.get("id", "?")))
        self._back_btn.setVisible(True)

    def _show_grid(self) -> None:
        self._stack.setCurrentIndex(0)
        self._title.setText("Packs")
        self._back_btn.setVisible(False)

    def _build_detail_page(self, pack: dict) -> QWidget:
        page = QFrame()
        page.setStyleSheet(f"background: {BG_BASE};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(16)

        # Header row: description + "Set Active" action
        header = QHBoxLayout()
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        desc = pack.get("description") or "No description provided."
        desc_lbl = QLabel(desc.strip())
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 13px;"
        )
        info_col.addWidget(desc_lbl)
        meta_bits = []
        if pack.get("author"):
            meta_bits.append(f"by {pack['author']}")
        if pack.get("license"):
            meta_bits.append(pack["license"])
        if pack.get("default_adapter"):
            meta_bits.append(f"adapter: {pack['default_adapter']}")
        meta = QLabel("  ·  ".join(meta_bits))
        meta.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px;"
        )
        info_col.addWidget(meta)
        header.addLayout(info_col, 1)

        action_col = QVBoxLayout()
        active_btn = QPushButton(
            "Active" if pack.get("id") == self._active_id
            else "Set Active"
        )
        active_btn.setCursor(Qt.PointingHandCursor)
        active_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_DARK};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {ACCENT}; }}
            QPushButton:disabled {{
                background: {BORDER}; color: {TEXT_MUTED};
            }}
        """)
        active_btn.setEnabled(pack.get("id") != self._active_id)
        active_btn.clicked.connect(
            lambda: self._on_set_active(pack)
        )
        action_col.addWidget(active_btn)
        action_col.addStretch()
        header.addLayout(action_col)

        layout.addLayout(header)

        # Slot grid — each slot is a clickable card
        slots = pack.get("slots", {}) or {}
        if not isinstance(slots, dict) or not slots:
            empty = QLabel("This pack has no slots defined.")
            empty.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 13px; "
                f"padding: 20px 0;"
            )
            layout.addWidget(empty)
            layout.addStretch()
            return page

        section_label = QLabel("SLOTS")
        section_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 0.06em; "
            f"padding-top: 8px;"
        )
        layout.addWidget(section_label)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        default_slot = pack.get("default_slot")
        for i, (slot_name, slot_value) in enumerate(slots.items()):
            card = self._make_slot_card(
                pack, slot_name, slot_value,
                is_default=(slot_name == default_slot),
            )
            r, c = divmod(i, 5)
            grid.addWidget(card, r, c)
        layout.addLayout(grid)
        layout.addStretch()
        return page

    def _make_slot_card(
        self,
        pack: dict,
        slot_name: str,
        slot_value,
        *,
        is_default: bool,
    ) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setObjectName("card")
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(180, 160)
        card.mousePressEvent = lambda _e: self._fire_slot(pack, slot_name, slot_value)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Show the slot's animation filename as a small preview
        file_label = QLabel(self._summarise_slot_value(slot_value))
        file_label.setAlignment(Qt.AlignCenter)
        file_label.setWordWrap(True)
        file_label.setStyleSheet(f"""
            background: {ACCENT_BG};
            color: {ACCENT_DARK};
            border-radius: 6px;
            padding: 18px 6px;
            font-size: 11px;
            font-weight: 600;
            min-height: 70px;
        """)
        layout.addWidget(file_label)

        name_lbl = QLabel(slot_name)
        name_lbl.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 13px; font-weight: 600;"
        )
        layout.addWidget(name_lbl)

        if is_default:
            badge = QLabel("default")
            badge.setStyleSheet(
                f"color: {ACCENT_DARK}; font-size: 10px; "
                f"font-weight: 600; letter-spacing: 0.04em;"
            )
            layout.addWidget(badge)

        return card

    @staticmethod
    def _summarise_slot_value(slot_value) -> str:
        """Render a slot's value (filename / list / dict) compactly."""
        if isinstance(slot_value, str):
            return Path(slot_value).name
        if isinstance(slot_value, list):
            return f"{len(slot_value)} variants"
        if isinstance(slot_value, dict):
            f = slot_value.get("file") or slot_value.get("name")
            return Path(str(f)).name if f else "dict"
        return str(slot_value)

    def _fire_slot(self, pack: dict, slot_name: str, slot_value) -> None:
        """Fire the slot's animation through the ctrl socket.

        Picks the bare filename stem so the animation node's existing
        mode resolver handles dispatch (same path used by the Library
        page).
        """
        if isinstance(slot_value, list):
            slot_value = slot_value[0] if slot_value else None
        if isinstance(slot_value, dict):
            slot_value = slot_value.get("file") or slot_value.get("name")
        if not slot_value:
            return
        stem = Path(str(slot_value)).stem
        self.ctrl.send(f"node animation mode on {stem}")

    def _on_set_active(self, pack: dict) -> None:
        pack_id = pack.get("id")
        if not pack_id:
            return
        self._write_active(pack_id)
        # Rebuild the grid so the active-badge updates, then re-show
        # the detail page so the "Active" button reflects state.
        new_grid = self._build_grid_page()
        old_grid = self._stack.widget(0)
        self._stack.removeWidget(old_grid)
        old_grid.deleteLater()
        self._stack.insertWidget(0, new_grid)
        self._grid_page = new_grid
        self._show_detail(pack)


class LearnPage(QWidget):
    """Education / Learn surface — chapter list + markdown viewer.

    Operator note (2026-06-10): "would be nice to have a little
    education tab to talk about animation, history, implementation,
    how our system works etc".

    Each chapter is a markdown file at ``docs/learn/<slug>.md``.
    Click a chapter on the left → it renders on the right.  Qt's
    ``QTextBrowser.setMarkdown()`` handles the rendering natively.

    To add a chapter: drop a new ``.md`` file in ``docs/learn/`` and
    append a (slug, title) tuple to ``LEARN_CHAPTERS`` at the top of
    this module.
    """

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar with title
        topbar = QFrame()
        topbar.setObjectName("topbar")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(28, 22, 28, 16)
        title = QLabel("Learn")
        title.setObjectName("page_title")
        tb.addWidget(title)
        tb.addStretch()
        sub = QLabel(
            "Animation, from cave painting to LED matrix"
        )
        sub.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 13px;"
        )
        tb.addWidget(sub)
        outer.addWidget(topbar)

        # Split: chapter list (left, narrow) + viewer (right)
        body = QSplitter(Qt.Horizontal)
        body.setStyleSheet(
            f"QSplitter::handle {{ background: {BORDER}; }}"
        )

        # ── chapter list ──────────────────────────────────────────
        self.chapters = QListWidget()
        self.chapters.setFixedWidth(260)
        self.chapters.setStyleSheet(f"""
            QListWidget {{
                background: {BG_BASE};
                border: none;
                border-right: 1px solid {BORDER};
                padding: 12px 0;
                font-size: 13px;
                outline: none;
            }}
            QListWidget::item {{
                color: {TEXT_MAIN};
                padding: 8px 20px;
                border: none;
            }}
            QListWidget::item:selected {{
                background: {ACCENT_BG};
                color: {ACCENT_DARK};
                font-weight: 600;
            }}
            QListWidget::item:hover {{
                background: {ACCENT_BG};
            }}
        """)
        for slug, title in LEARN_CHAPTERS:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, slug)
            self.chapters.addItem(item)
        self.chapters.currentRowChanged.connect(self._on_chapter_change)

        # ── viewer ────────────────────────────────────────────────
        viewer_frame = QFrame()
        viewer_frame.setStyleSheet(f"background: {BG_BASE};")
        viewer_layout = QVBoxLayout(viewer_frame)
        viewer_layout.setContentsMargins(28, 20, 28, 28)
        viewer_layout.setSpacing(0)

        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(True)
        self.viewer.setStyleSheet(f"""
            QTextBrowser {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 20px 28px;
                font-size: 14px;
                color: {TEXT_MAIN};
                font-family: -apple-system, "Segoe UI",
                             "Helvetica Neue", Arial, sans-serif;
            }}
        """)
        viewer_layout.addWidget(self.viewer)

        body.addWidget(self.chapters)
        body.addWidget(viewer_frame)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        outer.addWidget(body)

        # Default to the overview
        self.chapters.setCurrentRow(0)

    def _on_chapter_change(self, row: int) -> None:
        if row < 0 or row >= self.chapters.count():
            return
        item = self.chapters.item(row)
        slug = item.data(Qt.UserRole)
        path = LEARN_DIR / f"{slug}.md"
        if not path.is_file():
            self.viewer.setMarkdown(
                f"# Chapter missing\n\n"
                f"Expected at `docs/learn/{slug}.md` — file not "
                f"found.  Operator: add the file to populate this "
                f"chapter.\n"
            )
            return
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self.viewer.setPlainText(
                f"Failed to load {path.name}: {exc}"
            )
            return
        self.viewer.setMarkdown(text)


class HomePage(QWidget):
    """Operator dashboard — Phase 3 of the Tk supersede.

    Replaces the Home stub with a real surface combining the
    legacy Tk panel's Node Status / Nodes table / Quick controls
    into a coherent landing page.

    Sections:
      Hero card        — large active-animation status + Stop +
                          Open Mini Window shortcut
      Recent strip     — last N animations fired (persisted to
                          assets/recent.json)
      Diagnostics card — Nodes table fed by HealthService, with
                          per-node Stop + Reset.  Replaces the
                          Tk panel's Nodes overview.
    """

    RECENT_FILE = PROJECT_ROOT / "assets" / "recent.json"
    RECENT_MAX = 10

    def __init__(
        self,
        ctrl: "CtrlBridge",
        health,
        sidebar: "Sidebar",
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self.ctrl = ctrl
        self.health = health
        self.sidebar = sidebar
        self._recent: list[str] = self._load_recent()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar
        topbar = QFrame()
        topbar.setObjectName("topbar")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(28, 22, 28, 16)
        title = QLabel("Home")
        title.setObjectName("page_title")
        tb.addWidget(title)
        tb.addStretch()
        outer.addWidget(topbar)

        # Scrollable body so the dashboard works on shorter windows
        scroll = QScrollArea()
        scroll.setObjectName("scrollarea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QFrame()
        body.setStyleSheet(f"background: {BG_BASE};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 12, 28, 28)
        body_layout.setSpacing(16)

        body_layout.addWidget(self._build_hero())
        body_layout.addWidget(self._build_recent())
        body_layout.addWidget(self._build_diagnostics())
        body_layout.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll)

        # Refresh diagnostics on every health broadcast
        self.health.health_updated.connect(self._on_health)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._refresh_timer.start()

    # ── recent history ────────────────────────────────────────────

    def _load_recent(self) -> list[str]:
        if not self.RECENT_FILE.is_file():
            return []
        try:
            data = json.loads(self.RECENT_FILE.read_text())
            if isinstance(data, list):
                return [str(x) for x in data if isinstance(x, str)]
        except Exception:  # noqa: BLE001
            pass
        return []

    def _save_recent(self) -> None:
        try:
            self.RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.RECENT_FILE.write_text(
                json.dumps(self._recent[: self.RECENT_MAX], indent=2)
                + "\n"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[home] failed to persist recent.json: {exc}")

    def push_recent(self, name: str) -> None:
        """Companion calls this whenever an animation gets fired."""
        if not name:
            return
        if name in self._recent:
            self._recent.remove(name)
        self._recent.insert(0, name)
        self._recent = self._recent[: self.RECENT_MAX]
        self._save_recent()
        self._rebuild_recent_strip()

    # ── hero card ─────────────────────────────────────────────────

    def _build_hero(self) -> QWidget:
        card = QFrame()
        card.setProperty("class", "card")
        card.setStyleSheet(f"""
            QFrame[class="card"] {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {BG_CARD}, stop:1 {ACCENT_BG}
                );
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(2)
        eyebrow = QLabel("ACTIVE ANIMATION")
        eyebrow.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; "
            f"font-weight: 700; letter-spacing: 0.08em;"
        )
        left.addWidget(eyebrow)
        self._hero_mode = QLabel("(none)")
        self._hero_mode.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 26px; font-weight: 700;"
        )
        left.addWidget(self._hero_mode)
        self._hero_meta = QLabel("waiting for animation node…")
        self._hero_meta.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 13px;"
        )
        left.addWidget(self._hero_meta)
        layout.addLayout(left, 1)

        # Action column on the right
        actions = QVBoxLayout()
        actions.setSpacing(8)
        self._hero_stop = QPushButton("■ Stop")
        self._hero_stop.setCursor(Qt.PointingHandCursor)
        self._hero_stop.setStyleSheet(self._button_qss(danger=True))
        self._hero_stop.setEnabled(False)
        self._hero_stop.clicked.connect(self._on_stop_clicked)
        actions.addWidget(self._hero_stop)
        self._hero_library = QPushButton("Browse Library")
        self._hero_library.setCursor(Qt.PointingHandCursor)
        self._hero_library.setStyleSheet(self._button_qss())
        self._hero_library.clicked.connect(
            lambda: self.sidebar.select_default("Library")
        )
        actions.addWidget(self._hero_library)
        layout.addLayout(actions)
        return card

    # ── recent strip ──────────────────────────────────────────────

    def _build_recent(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background: {BG_BASE};")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(6)

        label = QLabel("RECENT")
        label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 0.06em;"
        )
        v.addWidget(label)

        self._recent_host = QFrame()
        self._recent_host.setStyleSheet("background: transparent;")
        self._recent_layout = QHBoxLayout(self._recent_host)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(8)
        v.addWidget(self._recent_host)
        self._rebuild_recent_strip()
        return wrap

    def _rebuild_recent_strip(self) -> None:
        while self._recent_layout.count():
            item = self._recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self._recent:
            empty = QLabel("Nothing yet — click a Library card to start.")
            empty.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 12px; "
                f"font-style: italic;"
            )
            self._recent_layout.addWidget(empty)
            self._recent_layout.addStretch()
            return
        for name in self._recent[: self.RECENT_MAX]:
            chip = QPushButton(name)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setStyleSheet(f"""
                QPushButton {{
                    background: {BG_CARD};
                    color: {TEXT_MAIN};
                    border: 1px solid {BORDER};
                    border-radius: 14px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    border-color: {ACCENT};
                    color: {ACCENT_DARK};
                }}
            """)
            chip.clicked.connect(
                lambda _checked=False, n=name: self._fire(n)
            )
            self._recent_layout.addWidget(chip)
        self._recent_layout.addStretch()

    # ── diagnostics card (nodes table) ────────────────────────────

    def _build_diagnostics(self) -> QWidget:
        card = QFrame()
        card.setProperty("class", "card")
        card.setStyleSheet(f"""
            QFrame[class="card"] {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Active nodes")
        title.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 15px; font-weight: 700;"
        )
        header.addWidget(title)
        header.addStretch()
        perf_btn = QPushButton("Open perf monitor")
        perf_btn.setCursor(Qt.PointingHandCursor)
        perf_btn.setStyleSheet(self._button_qss(small=True))
        perf_btn.clicked.connect(self._launch_perf_monitor)
        header.addWidget(perf_btn)
        layout.addLayout(header)

        # The table itself — header row + N data rows.  Header is
        # built once; rows + empty-state hint are rebuilt on every
        # health update via _refresh_nodes_table().
        self._nodes_host = QFrame()
        self._nodes_host.setStyleSheet("background: transparent;")
        self._nodes_layout = QVBoxLayout(self._nodes_host)
        self._nodes_layout.setContentsMargins(0, 0, 0, 0)
        self._nodes_layout.setSpacing(2)
        self._nodes_layout.addWidget(self._build_node_table_header())

        layout.addWidget(self._nodes_host)
        # First refresh paints the empty state (no health yet).
        self._refresh_nodes_table()
        return card

    def _build_node_table_header(self) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"background: {BG_BASE}; border-radius: 6px;"
        )
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(8)
        for label, w in (
            ("NODE", 80),
            ("MODE", 160),
            ("SIZE", 80),
            ("FPS", 50),
            ("MEM", 70),
            ("TX",  70),
            ("",   140),
        ):
            lbl = QLabel(label)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 10px; "
                f"font-weight: 700; letter-spacing: 0.06em;"
            )
            h.addWidget(lbl)
        return row

    def _refresh_nodes_table(self) -> None:
        # Remove every row except the header (index 0).  We
        # deleteLater() each widget — including any previous empty-
        # state QLabel — so this refresh has full control over what
        # populates below the header.
        while self._nodes_layout.count() > 1:
            item = self._nodes_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        nodes = self.health.known_nodes()
        if not nodes:
            # Recreate the empty-state QLabel from scratch every
            # refresh.  The previous attempt kept a self._nodes_empty
            # reference which got deleteLater()'d in the loop above,
            # then crashed on the next .setText() call with
            # "Internal C++ object already deleted".
            empty = QLabel(
                "Waiting for nodes — start <code>main.py</code> to "
                "populate."
            )
            empty.setTextFormat(Qt.RichText)
            empty.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 12px; "
                f"padding: 14px 0; font-style: italic;"
            )
            self._nodes_layout.addWidget(empty)
            return

        for node_id in nodes:
            snap = self.health.snapshot(node_id) or {}
            self._nodes_layout.addWidget(
                self._make_node_row(node_id, snap)
            )

    def _make_node_row(self, node_id: str, snap: dict) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: transparent; "
            f"border-bottom: 1px solid {BORDER}; }}"
        )
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)

        mode = snap.get("mode") or snap.get("data", {}).get("mode") or "?"
        size_block = snap.get("logical_size") or {}
        w = size_block.get("width", snap.get("w", "?"))
        ht = size_block.get("height", snap.get("h", "?"))
        fps = snap.get("fps_target", snap.get("fps", 0))
        mem = snap.get("memory_mb", snap.get("mem_mb", 0.0))
        tx = snap.get("tx_rate_mbps", 0.0)

        try:
            mem_str = f"{float(mem):.1f}"
        except (TypeError, ValueError):
            mem_str = "—"
        try:
            tx_str = f"{float(tx):.2f}"
        except (TypeError, ValueError):
            tx_str = "—"

        cells = [
            (node_id,          80, True),
            (str(mode),        160, False),
            (f"{w}×{ht}",      80, False),
            (str(fps),         50, False),
            (mem_str,          70, False),
            (tx_str,           70, False),
        ]
        for text, width, bold in cells:
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            weight = 700 if bold else 500
            lbl.setStyleSheet(
                f"color: {TEXT_MAIN}; font-size: 12px; "
                f"font-weight: {weight}; "
                f"background: transparent; border: none;"
            )
            h.addWidget(lbl)

        # Trailing action buttons: Stop + Reset (per-node)
        actions = QFrame()
        actions.setFixedWidth(140)
        actions.setStyleSheet("background: transparent; border: none;")
        ah = QHBoxLayout(actions)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(4)
        stop_btn = QPushButton("Stop")
        stop_btn.setCursor(Qt.PointingHandCursor)
        stop_btn.setStyleSheet(self._button_qss(small=True))
        stop_btn.clicked.connect(
            lambda _checked=False, n=node_id:
            self.ctrl.send(f"node {n} mode off")
        )
        ah.addWidget(stop_btn)
        reset_btn = QPushButton("Reset")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(self._button_qss(small=True))
        reset_btn.clicked.connect(
            lambda _checked=False, n=node_id:
            self.ctrl.send(f"node {n} mode reset")
        )
        ah.addWidget(reset_btn)
        h.addWidget(actions)
        return row

    # ── shared event glue ─────────────────────────────────────────

    def _on_health(self, node_id: str, payload: dict) -> None:
        if node_id == "animation":
            mode = (
                payload.get("mode")
                or payload.get("data", {}).get("mode")
                or "?"
            )
            self._hero_mode.setText(mode)
            size_block = payload.get("logical_size") or {}
            w = size_block.get("width", "?")
            h = size_block.get("height", "?")
            fps = payload.get("fps_target",
                              payload.get("fps", 0))
            mem = payload.get("memory_mb",
                              payload.get("mem_mb", 0.0))
            try:
                mem_str = f"{float(mem):.1f}MB"
            except (TypeError, ValueError):
                mem_str = "—"
            self._hero_meta.setText(
                f"{w}×{h} · {fps}fps · {mem_str}"
            )
            self._hero_stop.setEnabled(
                mode not in ("?", "", "solid_color")
            )
        self._refresh_nodes_table()

    def _refresh_all(self) -> None:
        # Periodic refresh — picks up no-broadcast staleness colour
        # transitions in case last_seen drifts past 5s without new
        # health.  Cheap; just redraws.
        self._refresh_nodes_table()

    # ── helpers ───────────────────────────────────────────────────

    def _fire(self, name: str) -> None:
        self.ctrl.send(f"node animation mode on {name}")
        self.push_recent(name)

    def _on_stop_clicked(self) -> None:
        self.ctrl.send("node animation mode off")

    def _launch_perf_monitor(self) -> None:
        script = GUI_DIR / "mochi_perf.py"
        if not script.is_file():
            return
        try:
            subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(GUI_DIR),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[home] perf launch failed: {exc}")

    def _button_qss(self, small: bool = False,
                    danger: bool = False) -> str:
        pad = "5px 10px" if small else "8px 14px"
        fs = "11px" if small else "13px"
        if danger:
            return f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_MAIN};
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                    padding: {pad};
                    font-size: {fs};
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: #fee2e2; color: #991b1b;
                    border-color: #fca5a5;
                }}
                QPushButton:disabled {{
                    color: {BORDER_HOVER};
                    border-color: {BORDER};
                }}
            """
        return f"""
            QPushButton {{
                background: transparent;
                color: {ACCENT_DARK};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: {pad};
                font-size: {fs};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {ACCENT_BG};
                border-color: {ACCENT};
            }}
        """


class EditorsPage(QWidget):
    """In-app launcher tiles for content-authoring tools.

    Replaces the Tk panel's "Launch Sprite Editor" button + adds
    the other editor entry points so the operator never has to
    cd / python tools/X.py from a terminal.

    Phase 5 of the Tk-supersede migration
    (docs/SUPERSEDE_TK_PLAN.md).

    Subprocess tracking matches the mini-window pattern —
    children get terminated on companion close.
    """

    EDITORS: list[dict] = [
        {
            "id": "sprite",
            "name": "Sprite Editor",
            "icon": "🧩",
            "desc": "Author + edit sprite sheets — grid + cells + "
                    "named frames.",
            "entry": "tools/sprite_editor_gui.py",
        },
        {
            "id": "bitmap",
            "name": "Bitmap Editor",
            "icon": "▦",
            "desc": "1-bit pixel grids for the smallest character "
                    "vocab.",
            "entry": "tools/bitmap_editor_gui.py",
        },
        {
            "id": "mscript",
            "name": "MochiScript Editor",
            "icon": "📜",
            "desc": "Visual editor for .mscript scripted sequences.",
            "entry": "tools/mscript_editor_gui.py",
        },
        {
            "id": "studio",
            "name": "Mochi Studio",
            "icon": "🎨",
            "desc": "All-in-one authoring environment.",
            "entry": "tools/mochi_studio.py",
        },
    ]

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._processes: list[subprocess.Popen] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(28, 22, 28, 16)
        title = QLabel("Editors")
        title.setObjectName("page_title")
        tb.addWidget(title)
        tb.addStretch()
        sub = QLabel(
            "Authoring tools.  Each launches as its own window."
        )
        sub.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 13px;"
        )
        tb.addWidget(sub)
        outer.addWidget(topbar)

        body = QFrame()
        body.setStyleSheet(f"background: {BG_BASE};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 20, 28, 28)
        body_layout.setSpacing(16)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(16)
        grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        for i, ed in enumerate(self.EDITORS):
            card = self._make_editor_card(ed)
            r, c = divmod(i, 3)
            grid.addWidget(card, r, c)
        body_layout.addLayout(grid)
        body_layout.addStretch()
        outer.addWidget(body)

    def _make_editor_card(self, ed: dict) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setStyleSheet(f"""
            QFrame[class="card"] {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}
            QFrame[class="card"]:hover {{
                border-color: {ACCENT};
            }}
        """)
        card.setFixedSize(280, 200)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        icon_lbl = QLabel(ed["icon"])
        icon_lbl.setStyleSheet(
            f"background: {ACCENT_BG}; color: {ACCENT_DARK}; "
            f"border-radius: 8px; font-size: 28px; "
            f"min-height: 48px; max-height: 48px; "
            f"min-width: 48px; max-width: 48px;"
        )
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        name = QLabel(ed["name"])
        name.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 15px; "
            f"font-weight: 700; padding-top: 6px;"
        )
        layout.addWidget(name)

        desc = QLabel(ed["desc"])
        desc.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px;"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addStretch()
        # Open button
        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch()
        btn = QPushButton("Open")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_DARK};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {ACCENT}; }}
            QPushButton:disabled {{
                background: {BORDER}; color: {TEXT_MUTED};
            }}
        """)
        entry = PROJECT_ROOT / ed["entry"]
        btn.setEnabled(entry.is_file())
        if not entry.is_file():
            btn.setToolTip(f"Missing: {ed['entry']}")
        btn.clicked.connect(
            lambda _checked=False, e=ed: self._open_editor(e)
        )
        button_row.addWidget(btn)
        layout.addLayout(button_row)
        return card

    def _open_editor(self, ed: dict) -> None:
        entry = PROJECT_ROOT / ed["entry"]
        if not entry.is_file():
            return
        try:
            proc = subprocess.Popen(
                [sys.executable, str(entry)],
                cwd=str(PROJECT_ROOT),
            )
            self._processes.append(proc)
        except Exception as exc:  # noqa: BLE001
            print(f"[editors] launch failed: {ed['entry']} — {exc}")

    def cleanup_subprocesses(self) -> None:
        """Called by CompanionMain on close — terminate any spawned
        editors so they don't orphan."""
        for proc in self._processes:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:  # noqa: BLE001
                    pass


class StubPage(QWidget):
    """Placeholder for tabs not yet wired (Home, Scenes, Triggers,
    Schedule, Editors, Settings)."""

    def __init__(self, title: str, phase: str, hint: str,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Page-title bar
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(28, 22, 28, 16)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("page_title")
        topbar_layout.addWidget(title_lbl)
        topbar_layout.addStretch()
        outer.addWidget(topbar)

        # Wondershare-style empty drop-zone
        body = build_empty_state(
            icon_glyph=_ICON_FOR_STUB.get(title, "✦"),
            heading=f"{title} — coming in {phase}",
            subtitle=hint,
            cta_label=None,            # stubs aren't actionable yet
        )
        outer.addWidget(body, 1)


# Per-tab glyph for the centered icon in StubPage's empty card.
# Picked to vaguely match each surface's purpose; replace with real
# SVG illustrations later.
_ICON_FOR_STUB: dict[str, str] = {
    "Home":     "✦",
    "Scenes":   "🎬",
    "Triggers": "⚡",
    "Schedule": "🕐",
    "Editors":  "🛠",
}


def build_empty_state(
    *,
    icon_glyph: str,
    heading: str,
    subtitle: str,
    cta_label: str | None = None,
    cta_on_click=None,
) -> QWidget:
    """Centred empty-state card with dashed drop-zone border, big
    icon, heading + subtitle, and an optional CTA button.

    Used by StubPage (Home/Scenes/Triggers/Schedule/Editors) and
    the Packs page's "No packs yet" state.  Visual matches the
    Wondershare reference (Converter empty state).
    """
    outer = QFrame()
    outer.setStyleSheet(f"background: {BG_BASE};")
    outer_layout = QVBoxLayout(outer)
    outer_layout.setContentsMargins(40, 40, 40, 40)
    outer_layout.setSpacing(0)

    # Dashed drop-zone box.  Qt's QFrame supports dashed borders via
    # QSS — we paint it on a wrapper card.
    zone = QFrame()
    zone.setStyleSheet(f"""
        QFrame {{
            background: {BG_CARD};
            border: 2px dashed {BORDER_HOVER};
            border-radius: 14px;
        }}
    """)
    zone_layout = QVBoxLayout(zone)
    zone_layout.setContentsMargins(40, 80, 40, 80)
    zone_layout.setSpacing(0)
    zone_layout.addStretch()

    # Centered icon
    icon = QLabel(icon_glyph)
    icon.setAlignment(Qt.AlignCenter)
    icon.setStyleSheet(f"""
        background: transparent;
        color: {ACCENT};
        font-size: 56px;
        padding-bottom: 16px;
    """)
    zone_layout.addWidget(icon)

    # Heading
    heading_lbl = QLabel(heading)
    heading_lbl.setAlignment(Qt.AlignHCenter)
    heading_lbl.setStyleSheet(f"""
        background: transparent;
        color: {TEXT_MAIN};
        font-size: 20px;
        font-weight: 600;
        padding: 6px 0;
    """)
    zone_layout.addWidget(heading_lbl)

    # Subtitle
    sub_lbl = QLabel(subtitle)
    sub_lbl.setAlignment(Qt.AlignHCenter)
    sub_lbl.setStyleSheet(f"""
        background: transparent;
        color: {TEXT_MUTED};
        font-size: 13px;
        padding: 0 60px 12px 60px;
    """)
    sub_lbl.setWordWrap(True)
    sub_lbl.setTextFormat(Qt.RichText)
    zone_layout.addWidget(sub_lbl)

    # Optional CTA button
    if cta_label:
        cta_row = QHBoxLayout()
        cta_row.addStretch()
        cta = QPushButton(cta_label)
        cta.setCursor(Qt.PointingHandCursor)
        cta.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_DARK};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 22px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {ACCENT}; }}
        """)
        if cta_on_click:
            cta.clicked.connect(cta_on_click)
        cta_row.addWidget(cta)
        cta_row.addStretch()
        zone_layout.addSpacing(10)
        zone_layout.addLayout(cta_row)

    zone_layout.addStretch()
    outer_layout.addWidget(zone, 1)
    return outer


# ── sidebar ────────────────────────────────────────────────────────

SIDEBAR_ITEMS: list[tuple[str, str]] = [
    ("Home",     "🏠"),
    ("Library",  "📚"),
    ("Packs",    "🎭"),
    ("Scenes",   "🎬"),
    ("Triggers", "⚡"),
    ("Schedule", "🕐"),
    ("Editors",  "🛠"),
    ("Learn",    "🎓"),
    ("Settings", "⚙"),
]


class Sidebar(QWidget):
    item_selected = Signal(str)
    pin_clicked = Signal(str)   # animation name to fire

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        self._pinned: list[str] = self._load_pinned()
        self._pin_buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._layout = layout

        # Logo row: small purple mark + brand text.  Borrows the
        # Wondershare layout (icon-mark on the left, brand text to
        # the right).
        logo_row = QFrame()
        logo_row.setStyleSheet(f"background: {BG_SIDEBAR}; border: none;")
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(20, 18, 20, 20)
        logo_layout.setSpacing(10)

        mark = QLabel("◆")
        mark.setFixedSize(28, 28)
        mark.setAlignment(Qt.AlignCenter)
        mark.setStyleSheet(f"""
            background: {ACCENT_DARK};
            color: white;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 700;
        """)
        logo_layout.addWidget(mark)

        logo = QLabel("MOCHI")
        logo.setObjectName("sidebar_logo")
        logo.setStyleSheet(f"""
            background: transparent;
            color: {TEXT_MAIN};
            font-size: 18px;
            font-weight: 700;
            padding: 0;
        """)
        logo_layout.addWidget(logo)
        logo_layout.addStretch()

        layout.addWidget(logo_row)

        self._buttons: dict[str, QPushButton] = {}
        for label, icon in SIDEBAR_ITEMS:
            btn = QPushButton(f"  {icon}    {label}")
            btn.setProperty("class", "sidebar_btn")
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda _checked=False, l=label: self._select(l)
            )
            self._buttons[label] = btn
            layout.addWidget(btn)

        # ── PINNED section (operator's "Quick Access" shortcuts) ──
        # Matches the Wondershare reference: section header with a
        # right-aligned "+" button to add new pins.  Each pin is a
        # one-click shortcut that fires that animation.
        pinned_header = QFrame()
        ph_layout = QHBoxLayout(pinned_header)
        ph_layout.setContentsMargins(20, 16, 12, 6)
        ph_layout.setSpacing(0)
        pinned_label = QLabel("PINNED")
        pinned_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 0.06em; "
            f"background: transparent;"
        )
        ph_layout.addWidget(pinned_label)
        ph_layout.addStretch()
        self._add_pin_btn = QPushButton("＋")
        self._add_pin_btn.setFixedSize(22, 22)
        self._add_pin_btn.setCursor(Qt.PointingHandCursor)
        self._add_pin_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 4px;
                font-size: 14px;
                font-weight: 600;
                padding: 0;
            }}
            QPushButton:hover {{
                background: {ACCENT_BG};
                color: {ACCENT_DARK};
                border-color: {ACCENT};
            }}
        """)
        self._add_pin_btn.clicked.connect(self._on_add_pin)
        ph_layout.addWidget(self._add_pin_btn)
        layout.addWidget(pinned_header)

        # Container that holds the pin buttons (so we can rebuild on
        # add/remove without reshuffling the entire layout).
        self._pins_container = QFrame()
        self._pins_container.setStyleSheet(
            f"background: {BG_SIDEBAR}; border: none;"
        )
        pc_layout = QVBoxLayout(self._pins_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)
        pc_layout.setSpacing(0)
        self._pins_layout = pc_layout
        layout.addWidget(self._pins_container)
        self._rebuild_pins()

        layout.addStretch()

        # ── Bottom promo card — Jenkins Robotics ──────────────────
        # Borrows Wondershare's "UniConverter 17 / Perpetual plan /
        # Up to 60% OFF / Upgrade Now" layout but replaces the
        # upgrade nudge with channel + Patreon CTAs.  Operator's
        # standing brief: "promote jenkins robotics, the youtube
        # channel, patreon etc".
        promo = QFrame()
        promo.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_DARK},
                    stop:1 #5b21b6
                );
                border-radius: 10px;
            }}
        """)
        promo_layout = QVBoxLayout(promo)
        promo_layout.setContentsMargins(14, 14, 14, 14)
        promo_layout.setSpacing(6)

        brand = QLabel("Jenkins Robotics")
        brand.setStyleSheet("""
            background: transparent;
            color: white;
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.02em;
        """)
        promo_layout.addWidget(brand)

        tag = QLabel("Open robotics + AI · tutorials weekly")
        tag.setStyleSheet("""
            background: transparent;
            color: rgba(255, 255, 255, 0.85);
            font-size: 10px;
            font-weight: 500;
        """)
        tag.setWordWrap(True)
        promo_layout.addWidget(tag)
        promo_layout.addSpacing(8)

        # Two side-by-side CTAs
        cta_row = QHBoxLayout()
        cta_row.setContentsMargins(0, 0, 0, 0)
        cta_row.setSpacing(6)

        yt_btn = QPushButton("YouTube")
        yt_btn.setCursor(Qt.PointingHandCursor)
        yt_btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #5b21b6;
                border: none;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover { background: #f5f3ff; }
        """)
        yt_btn.clicked.connect(lambda: self._open_promo_url(
            "https://www.youtube.com/@Jenkins_Robotics"
        ))
        cta_row.addWidget(yt_btn)

        pt_btn = QPushButton("Patreon")
        pt_btn.setCursor(Qt.PointingHandCursor)
        pt_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        pt_btn.clicked.connect(lambda: self._open_promo_url(
            "https://www.patreon.com/JenkinsRobotics"
        ))
        cta_row.addWidget(pt_btn)

        promo_layout.addLayout(cta_row)

        # Wrap the promo in a margin frame so it doesn't touch the
        # sidebar edges.
        promo_wrap = QFrame()
        promo_wrap.setStyleSheet(f"background: {BG_SIDEBAR};")
        wrap_layout = QVBoxLayout(promo_wrap)
        wrap_layout.setContentsMargins(12, 0, 12, 16)
        wrap_layout.addWidget(promo)
        layout.addWidget(promo_wrap)

    def _select(self, label: str) -> None:
        for l, btn in self._buttons.items():
            btn.setChecked(l == label)
        # Clear pin selection visual when a top-nav row is picked.
        # _pin_buttons can contain the empty-state QLabel hint, which
        # doesn't have setChecked — skip non-button entries.
        for pb in self._pin_buttons:
            if isinstance(pb, QPushButton):
                pb.setChecked(False)
        self.item_selected.emit(label)

    def select_default(self, label: str = "Library") -> None:
        if label in self._buttons:
            self._buttons[label].click()

    # ── Pinned shortcuts ──────────────────────────────────────────

    def _load_pinned(self) -> list[str]:
        if not PINNED_FILE.is_file():
            return []
        try:
            data = json.loads(PINNED_FILE.read_text())
            if isinstance(data, list):
                return [str(x) for x in data if isinstance(x, str)]
        except Exception:  # noqa: BLE001
            pass
        return []

    def _save_pinned(self) -> None:
        try:
            PINNED_FILE.parent.mkdir(parents=True, exist_ok=True)
            PINNED_FILE.write_text(
                json.dumps(self._pinned, indent=2) + "\n"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[sidebar] failed to persist pinned.json: {exc}")

    def _rebuild_pins(self) -> None:
        # Clear existing pin buttons
        for btn in self._pin_buttons:
            btn.deleteLater()
        self._pin_buttons = []
        # Empty hint when no pins yet
        if not self._pinned:
            hint = QLabel("Click + to pin an animation")
            hint.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px; "
                f"font-style: italic; padding: 4px 20px 8px 20px; "
                f"background: transparent;"
            )
            hint.setObjectName("pin_empty_hint")
            self._pins_layout.addWidget(hint)
            self._pin_buttons.append(hint)
            return
        # Render each pin as a sidebar button
        for name in self._pinned:
            btn = QPushButton(f"  ★    {name}")
            btn.setProperty("class", "sidebar_btn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setContextMenuPolicy(Qt.NoContextMenu)
            btn.clicked.connect(
                lambda _checked=False, n=name: self._on_pin_click(n)
            )
            # Right-click → remove.  Qt's QPushButton doesn't expose a
            # context menu directly, so we hijack on a long-press via
            # the alt key in mousePressEvent.  Simpler: bind shift+click
            # to remove for now (documented quirk).
            self._pin_buttons.append(btn)
            self._pins_layout.addWidget(btn)

    def _on_pin_click(self, name: str) -> None:
        # Don't propagate as item_selected (that's for top-nav items).
        # Visual: mark the clicked pin button as checked, clear the
        # rest of the nav.
        for l, b in self._buttons.items():
            b.setChecked(False)
        for pb in self._pin_buttons:
            if isinstance(pb, QPushButton):
                pb.setChecked(pb.text().endswith(name))
        self.pin_clicked.emit(name)

    def _open_promo_url(self, url: str) -> None:
        try:
            QDesktopServices.openUrl(QUrl(url))
        except Exception as exc:  # noqa: BLE001
            print(f"[sidebar] failed to open {url}: {exc}")

    def _on_add_pin(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Pin an animation",
            "Animation name (must match the Library):",
        )
        if not ok:
            return
        name = (text or "").strip()
        if not name:
            return
        if name in self._pinned:
            return
        self._pinned.append(name)
        self._save_pinned()
        self._rebuild_pins()


# ── main window ────────────────────────────────────────────────────

class CompanionMain(QMainWindow):
    def __init__(self, ctrl_addr: str,
                 health_addr: str = DEFAULT_HEALTH_ADDR) -> None:
        super().__init__()
        self.logger = logging.getLogger("MochiCompanion")
        self.setWindowTitle("Mochi Companion")
        self.resize(1280, 820)
        self.setStyleSheet(STYLESHEET)

        self.ctrl = CtrlBridge(ctrl_addr, self.logger)
        # Shared HealthService — Phase 1 of the Tk-supersede migration.
        # Pages can subscribe via ``self.health.health_updated`` or
        # poll via ``self.health.snapshot(node_id)``.  Today no
        # consumer is wired; Phase 2 adds the toolbar status pill.
        from mochi_health_service import HealthService
        self.health = HealthService(
            health_sub_addr=health_addr,
            logger=self.logger,
        )
        self.health.health_updated.connect(self._on_health_updated)
        self.health.error.connect(self._on_health_error)
        self._mini_proc: subprocess.Popen | None = None
        self._available_skins: list[dict] = discover_skins()

        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.item_selected.connect(self._on_sidebar_select)
        self.sidebar.pin_clicked.connect(self._on_pin_clicked)
        h.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        # ── top toolbar (always visible, above the page stack) ────
        toolbar = QFrame()
        toolbar.setStyleSheet(
            f"background: {BG_BASE}; border-bottom: 1px solid {BORDER};"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(20, 8, 20, 8)
        toolbar_layout.setSpacing(8)

        # ── status pill (left) — Phase 2 of Tk supersede ─────────
        self.status_pill = self._build_status_pill()
        toolbar_layout.addWidget(self.status_pill)

        # ── Stop button — sends "mode off" to the animation node ─
        # Replaces the Tk panel's "Turn Off" button.  Disabled when
        # no animation is currently active.
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setToolTip("Stop the active animation")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #fee2e2;
                color: #991b1b;
                border-color: #fca5a5;
            }}
            QPushButton:disabled {{
                background: transparent;
                color: {BORDER_HOVER};
                border-color: {BORDER};
            }}
        """)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        toolbar_layout.addWidget(self.stop_btn)

        toolbar_layout.addStretch()

        # ── community / promo / help icon row ────────────────────
        # Borrows the Wondershare top-right chrome (avatar / gift /
        # chat / headset).  Each opens an external URL in the
        # default browser.  Hover label appears via setToolTip.
        community_row = self._build_community_icons()
        toolbar_layout.addWidget(community_row)

        # Visual divider between community icons and the mini-window
        # button.
        divider = QFrame()
        divider.setFixedSize(1, 24)
        divider.setStyleSheet(f"background: {BORDER};")
        toolbar_layout.addSpacing(6)
        toolbar_layout.addWidget(divider)
        toolbar_layout.addSpacing(6)

        self.mini_btn = QPushButton(self._mini_button_label())
        self.mini_btn.setCursor(Qt.PointingHandCursor)
        self.mini_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_DARK};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {ACCENT};
            }}
        """)
        self.mini_btn.clicked.connect(self._on_mini_toggle)
        toolbar_layout.addWidget(self.mini_btn)
        right.addWidget(toolbar)

        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)

        right_container = QWidget()
        right_container.setLayout(right)
        h.addWidget(right_container, 1)

        # Build pages
        self.pages: dict[str, QWidget] = {}
        self.pages["Home"] = HomePage(
            self.ctrl, self.health, self.sidebar,
        )
        self.pages["Library"] = LibraryPage(self.ctrl)
        packs_page = PacksPage(self.ctrl)
        packs_page.navigate.connect(self.sidebar.select_default)
        self.pages["Packs"] = packs_page
        self.pages["Scenes"] = StubPage(
            "Scenes", "Phase B",
            "Curated bundles of idle pool + reaction pool + triggers."
            "  Chill / Hype / Focus / Sleepy / Party / Drive / "
            "Pomodoro / Festival.",
        )
        self.pages["Triggers"] = StubPage(
            "Triggers", "Phase C",
            "Rows of Source → Asset.  Sources: ZMQ topics, timers, "
            "time-of-day, file watchers, MQTT.  The bus stops being "
            "plumbing and becomes a feature.",
        )
        self.pages["Schedule"] = StubPage(
            "Schedule", "Phase B",
            "Cron-style showtimes.  Weekdays 9-12 → Focus.  Friday "
            "5pm → Party.  11pm-7am → Sleep.",
        )
        self.pages["Editors"] = EditorsPage()
        self.pages["Learn"] = LearnPage()
        # Settings page — minimal first version with skin list.
        # Full picker (radio + preview) lands when there's >1 skin
        # to choose between.
        self.pages["Settings"] = self._build_settings_page()

        for name, page in self.pages.items():
            self.stack.addWidget(page)

        self.sidebar.select_default("Library")

    def _on_sidebar_select(self, label: str) -> None:
        page = self.pages.get(label)
        if page is not None:
            self.stack.setCurrentWidget(page)

    # ── HealthService glue (Phase 1 + Phase 2) ────────────────────

    def _build_status_pill(self) -> QFrame:
        """Top-toolbar live status pill.  Reflects the animation
        node's latest health broadcast — colour shifts grey → green
        as health arrives, grey again when it goes stale (~5s old).
        """
        pill = QFrame()
        pill.setCursor(Qt.PointingHandCursor)
        pill.setStyleSheet(self._pill_qss("grey"))
        layout = QHBoxLayout(pill)
        layout.setContentsMargins(10, 5, 12, 5)
        layout.setSpacing(8)
        self._pill_dot = QLabel("●")
        self._pill_dot.setStyleSheet(
            "color: #9ca3af; font-size: 11px; background: transparent;"
        )
        layout.addWidget(self._pill_dot)
        self._pill_label = QLabel("waiting for animation node…")
        self._pill_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; "
            f"font-weight: 600; background: transparent;"
        )
        layout.addWidget(self._pill_label)
        # Clicking the pill jumps to Home (where the diagnostics
        # panel lives in Phase 3).
        pill.mousePressEvent = lambda _e: self.sidebar.select_default("Home")

        # Refresh the pill at 1Hz so staleness fades it grey when
        # health stops flowing.
        self._pill_timer = QTimer(self)
        self._pill_timer.setInterval(1000)
        self._pill_timer.timeout.connect(self._refresh_status_pill)
        self._pill_timer.start()
        return pill

    def _pill_qss(self, state: str) -> str:
        # state ∈ {"green", "grey", "red"}
        if state == "green":
            bg, border, txt = "#dcfce7", "#86efac", "#166534"
        elif state == "red":
            bg, border, txt = "#fee2e2", "#fca5a5", "#991b1b"
        else:
            bg, border, txt = "#f3f4f6", "#e5e7eb", "#6b7280"
        return f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
        """

    def _on_health_updated(self, node_id: str, payload: dict) -> None:
        """Update the status pill + Stop button enable state."""
        if node_id != "animation":
            return
        mode = (
            payload.get("mode")
            or payload.get("data", {}).get("mode")
            or "?"
        )
        size_block = payload.get("logical_size") or {}
        w = size_block.get("width", payload.get("w", "?"))
        h = size_block.get("height", payload.get("h", "?"))
        fps = payload.get("fps_target", payload.get("fps", 0))
        mem = payload.get("memory_mb", payload.get("mem_mb", 0.0))

        try:
            mem_str = f"{float(mem):.1f}MB"
        except (TypeError, ValueError):
            mem_str = "—"
        self._pill_label.setText(
            f"animation · {mode} · {w}×{h} · {fps}fps · {mem_str}"
        )

        # Enable Stop when an animation is actively rendering.
        # Heuristic: any mode that isn't the fallback "solid_color"
        # counts as "running".
        is_running = mode not in ("?", "", "solid_color")
        self.stop_btn.setEnabled(is_running)
        self._refresh_status_pill()

    def _refresh_status_pill(self) -> None:
        """Re-evaluate freshness colour without a new broadcast."""
        if not hasattr(self, "health"):
            return
        from mochi_health_service import staleness
        last = self.health.last_seen("animation")
        state = staleness(last)
        if state == "fresh":
            self.status_pill.setStyleSheet(self._pill_qss("green"))
            self._pill_dot.setStyleSheet(
                "color: #16a34a; font-size: 11px; background: transparent;"
            )
            self._pill_label.setStyleSheet(
                "color: #166534; font-size: 12px; "
                "font-weight: 600; background: transparent;"
            )
        else:
            self.status_pill.setStyleSheet(self._pill_qss("grey"))
            self._pill_dot.setStyleSheet(
                "color: #9ca3af; font-size: 11px; background: transparent;"
            )
            self._pill_label.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 12px; "
                f"font-weight: 600; background: transparent;"
            )
            if state == "gone":
                # If health never arrived, keep the waiting message.
                # If it WAS fresh but stopped, mark as stale.
                if last is not None:
                    self._pill_label.setText("animation · stale")
                    self.stop_btn.setEnabled(False)

    def _on_stop_clicked(self) -> None:
        """Send "mode off" to the animation node.  Matches the Tk
        panel's Turn Off button behaviour exactly."""
        self.ctrl.send("node animation mode off")
        self.logger.info("Stop clicked — sent 'mode off'")

    def _on_health_error(self, msg: str) -> None:
        self.logger.warning("HealthService: %s", msg)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Lazy-start the health service the first time the window
        # appears so headless smoke tests don't pay for the SUB
        # connection.
        if hasattr(self, "health") and self.health._thread is None:
            self.health.start()

    def _on_pin_clicked(self, name: str) -> None:
        """Pinned sidebar shortcut fired — dispatch through the same
        ctrl path the Library card uses."""
        if not name:
            return
        self.ctrl.send(f"node animation mode on {name}")
        self.logger.info("pin fired — %s", name)
        # Record into Home's recent strip if Home is up.
        home = self.pages.get("Home")
        if isinstance(home, HomePage):
            home.push_recent(name)

    # ── community / promo icon row ────────────────────────────────

    COMMUNITY_LINKS: list[tuple[str, str, str]] = [
        # (glyph, tooltip, url)
        ("▶",  "Jenkins Robotics on YouTube",
                "https://www.youtube.com/@Jenkins_Robotics"),
        ("♥",  "Support on Patreon",
                "https://www.patreon.com/JenkinsRobotics"),
        ("◯",  "Discord / community",
                "https://www.youtube.com/@Jenkins_Robotics"),
        ("?",  "Help & docs",
                "https://github.com/jonathanjenkins/Mochi"),
    ]

    def _build_community_icons(self) -> QWidget:
        row = QFrame()
        row.setStyleSheet(f"background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        for glyph, tooltip, url in self.COMMUNITY_LINKS:
            btn = QPushButton(glyph)
            btn.setFixedSize(30, 30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_MUTED};
                    border: none;
                    border-radius: 6px;
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {ACCENT_BG};
                    color: {ACCENT_DARK};
                }}
            """)
            btn.clicked.connect(
                lambda _checked=False, u=url: self._open_url(u)
            )
            row_layout.addWidget(btn)
        return row

    def _open_url(self, url: str) -> None:
        try:
            QDesktopServices.openUrl(QUrl(url))
            self.logger.info("opened: %s", url)
        except Exception as exc:  # noqa: BLE001
            self.logger.error("failed to open %s: %s", url, exc)

    def _build_settings_page(self) -> QWidget:
        """Settings — three sub-sections after Phase 4 of the Tk
        supersede:

          Skins        (existing) — body frame picker
          Renderer     (Advanced) — colour + matrix size knobs
                                     migrated from the Tk panel
          Diagnostics  (Advanced) — raw command + quit node

        Advanced sections are hidden behind a toggle button at the
        top of the page so casual users don't see the sharp edges.
        """
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(28, 22, 28, 16)
        title = QLabel("Settings")
        title.setObjectName("page_title")
        tb.addWidget(title)
        tb.addStretch()
        # Advanced toggle
        self._advanced_toggle = QPushButton("Show advanced")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setCursor(Qt.PointingHandCursor)
        self._advanced_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {ACCENT_BG}; color: {ACCENT_DARK};
                border-color: {ACCENT};
            }}
            QPushButton:checked {{
                background: {ACCENT_BG}; color: {ACCENT_DARK};
                border-color: {ACCENT};
            }}
        """)
        self._advanced_toggle.clicked.connect(self._toggle_advanced)
        tb.addWidget(self._advanced_toggle)
        outer.addWidget(topbar)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setObjectName("scrollarea")
        scroll.setWidgetResizable(True)
        body = QFrame()
        body.setStyleSheet(f"background: {BG_BASE};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 20, 28, 28)
        body_layout.setSpacing(20)

        # ── Skins (always visible) ─────────────────────────────
        body_layout.addWidget(self._build_skins_section())

        # ── Renderer (advanced) ────────────────────────────────
        self._renderer_section = self._build_renderer_section()
        self._renderer_section.setVisible(False)
        body_layout.addWidget(self._renderer_section)

        # ── Diagnostics (advanced) ─────────────────────────────
        self._diag_section = self._build_diagnostics_section()
        self._diag_section.setVisible(False)
        body_layout.addWidget(self._diag_section)

        body_layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        return page

    def _toggle_advanced(self, checked: bool) -> None:
        self._renderer_section.setVisible(checked)
        self._diag_section.setVisible(checked)
        self._advanced_toggle.setText(
            "Hide advanced" if checked else "Show advanced"
        )

    # ── Skins section ────────────────────────────────────────────

    def _build_skins_section(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background: {BG_BASE};")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        heading = QLabel("Skins")
        heading.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 16px; font-weight: 700;"
        )
        layout.addWidget(heading)

        sub = QLabel(
            "Body frames the mini window wears.  Drop folders "
            "under <code>assets/skins/&lt;id&gt;/</code> with "
            "<code>body.png</code> + <code>meta.yaml</code>.  See "
            "<code>docs/SKIN_CONVENTION.md</code>."
        )
        sub.setTextFormat(Qt.RichText)
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        if not self._available_skins:
            empty = QLabel("(no skins detected)")
            empty.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 13px; "
                f"padding: 12px 0;"
            )
            layout.addWidget(empty)
        else:
            for skin in self._available_skins:
                row = QFrame()
                row.setProperty("class", "card")
                row.setStyleSheet(f"""
                    QFrame[class="card"] {{
                        background: {BG_CARD};
                        border: 1px solid {BORDER};
                        border-radius: 8px;
                    }}
                """)
                rl = QHBoxLayout(row)
                rl.setContentsMargins(14, 12, 14, 12)
                rl.setSpacing(12)
                name = QLabel(skin.get("name", skin.get("id", "?")))
                name.setStyleSheet(
                    f"color: {TEXT_MAIN}; font-size: 13px; "
                    f"font-weight: 600;"
                )
                rl.addWidget(name)
                rl.addSpacing(12)
                meta_bits = []
                bbox = skin.get("screen_bbox")
                if bbox:
                    meta_bits.append(
                        f"screen {bbox[2]}×{bbox[3]} @ "
                        f"({bbox[0]}, {bbox[1]})"
                    )
                if skin.get("author"):
                    meta_bits.append(f"by {skin['author']}")
                if skin.get("_warning"):
                    meta_bits.append(f"⚠ {skin['_warning']}")
                meta = QLabel("  ·  ".join(meta_bits))
                meta.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 12px;"
                )
                rl.addWidget(meta)
                rl.addStretch()
                layout.addWidget(row)
        return wrap

    # ── Renderer section (Tk-migrated) ────────────────────────────

    def _build_renderer_section(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background: {BG_BASE};")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        heading = QLabel("Renderer (advanced)")
        heading.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 16px; font-weight: 700;"
        )
        layout.addWidget(heading)
        sub = QLabel(
            "Animation-node knobs migrated from the legacy "
            "Tk debug panel.  Most operators won't need these."
        )
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Matrix size row
        size_row = self._setting_row(
            "Logical canvas size",
            "W×H of the renderer's output buffer.",
        )
        self._size_entry = QLineEdit()
        self._size_entry.setPlaceholderText("64x64")
        self._size_entry.setText("64x64")
        self._size_entry.setMaximumWidth(120)
        self._size_entry.setStyleSheet(self._line_qss())
        size_btn = QPushButton("Apply")
        size_btn.setCursor(Qt.PointingHandCursor)
        size_btn.setStyleSheet(self._button_qss_settings())
        size_btn.clicked.connect(self._apply_size)
        size_row.layout().addWidget(self._size_entry)
        size_row.layout().addWidget(size_btn)
        size_row.layout().addStretch()
        layout.addWidget(size_row)

        # Solid colour row
        colour_row = self._setting_row(
            "Solid colour fallback",
            "RGB used when an animation can't render.",
        )
        self._rgb_entry = QLineEdit()
        self._rgb_entry.setPlaceholderText("255 120 40")
        self._rgb_entry.setText("255 120 40")
        self._rgb_entry.setMaximumWidth(120)
        self._rgb_entry.setStyleSheet(self._line_qss())
        self._colour_target = QComboBox()
        self._colour_target.addItems(["current", "solid_color"])
        self._colour_target.setStyleSheet(self._line_qss())
        colour_btn = QPushButton("Send")
        colour_btn.setCursor(Qt.PointingHandCursor)
        colour_btn.setStyleSheet(self._button_qss_settings())
        colour_btn.clicked.connect(self._apply_colour)
        colour_row.layout().addWidget(self._rgb_entry)
        colour_row.layout().addWidget(self._colour_target)
        colour_row.layout().addWidget(colour_btn)
        colour_row.layout().addStretch()
        layout.addWidget(colour_row)

        # Reset row
        reset_row = self._setting_row(
            "Reset current mode",
            "Re-activate the current animation from scratch.",
        )
        reset_btn = QPushButton("Reset")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(self._button_qss_settings())
        reset_btn.clicked.connect(
            lambda: self.ctrl.send("node animation mode reset")
        )
        reset_row.layout().addWidget(reset_btn)
        reset_row.layout().addStretch()
        layout.addWidget(reset_row)
        return wrap

    # ── Diagnostics section (Tk-migrated) ─────────────────────────

    def _build_diagnostics_section(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet(f"background: {BG_BASE};")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        heading = QLabel("Diagnostics (advanced)")
        heading.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 16px; font-weight: 700;"
        )
        layout.addWidget(heading)
        sub = QLabel(
            "Debug surface for power users.  Replaces the Tk "
            "panel's Raw Command + Quit Node + helper launchers."
        )
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        # Raw command row
        cmd_row = self._setting_row(
            "Send raw ctrl command",
            "Anything you'd type into the bus.  Examples: "
            "<code>node animation size 64x64</code>, "
            "<code>play assets/mscripts/demo_wink.mscript</code>.",
        )
        self._raw_entry = QLineEdit()
        self._raw_entry.setPlaceholderText(
            "node animation mode on rainbow"
        )
        self._raw_entry.setStyleSheet(self._line_qss())
        self._raw_entry.returnPressed.connect(self._send_raw)
        cmd_send = QPushButton("Send")
        cmd_send.setCursor(Qt.PointingHandCursor)
        cmd_send.setStyleSheet(self._button_qss_settings())
        cmd_send.clicked.connect(self._send_raw)
        cmd_row.layout().addWidget(self._raw_entry, 1)
        cmd_row.layout().addWidget(cmd_send)
        layout.addWidget(cmd_row)

        # Quit node row
        quit_row = self._setting_row(
            "Stop animation node",
            "Sends <code>quit</code> to the animation node's "
            "ctrl socket.  Use sparingly — main.py won't "
            "auto-relaunch.",
        )
        quit_btn = QPushButton("Quit Node")
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.setStyleSheet(self._button_qss_settings(danger=True))
        quit_btn.clicked.connect(lambda: self.ctrl.send("quit"))
        quit_row.layout().addWidget(quit_btn)
        quit_row.layout().addStretch()
        layout.addWidget(quit_row)
        return wrap

    # ── helpers ──────────────────────────────────────────────────

    def _setting_row(self, label: str, hint: str) -> QFrame:
        row = QFrame()
        row.setProperty("class", "card")
        row.setStyleSheet(f"""
            QFrame[class="card"] {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(4)
        title = QLabel(label)
        title.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 13px; "
            f"font-weight: 600;"
        )
        outer.addWidget(title)
        hint_lbl = QLabel(hint)
        hint_lbl.setTextFormat(Qt.RichText)
        hint_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px;"
        )
        hint_lbl.setWordWrap(True)
        outer.addWidget(hint_lbl)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 6, 0, 0)
        controls.setSpacing(8)
        outer.addLayout(controls)
        return row

    def _line_qss(self) -> str:
        return f"""
            QLineEdit, QComboBox {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                color: {TEXT_MAIN};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {ACCENT};
            }}
        """

    def _button_qss_settings(self, danger: bool = False) -> str:
        if danger:
            return f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_MAIN};
                    border: 1px solid {BORDER};
                    border-radius: 6px;
                    padding: 5px 14px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: #fee2e2; color: #991b1b;
                    border-color: #fca5a5;
                }}
            """
        return f"""
            QPushButton {{
                background: {ACCENT_DARK};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 5px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {ACCENT}; }}
        """

    def _apply_size(self) -> None:
        size = self._size_entry.text().strip()
        if "x" not in size.lower():
            return
        self.ctrl.send(f"node animation size {size}")

    def _apply_colour(self) -> None:
        parts = self._rgb_entry.text().split()
        if len(parts) != 3:
            return
        try:
            r, g, b = (int(p) for p in parts)
        except ValueError:
            return
        target = self._colour_target.currentText()
        if target == "current":
            self.ctrl.send(f"node animation color {r} {g} {b}")
        else:
            self.ctrl.send(
                f"node animation color {target} {r} {g} {b}"
            )

    def _send_raw(self) -> None:
        text = self._raw_entry.text().strip()
        if not text:
            return
        self.ctrl.send(text)
        self.logger.info("raw command sent: %s", text)
        self._raw_entry.clear()

    # ── mini-window toolbar control ──────────────────────────────

    def _mini_button_label(self) -> str:
        """Toggle text reflects current state."""
        if self._mini_proc is not None and self._mini_proc.poll() is None:
            return "Close Mini Window"
        return "Open Mini Window"

    def _refresh_mini_button(self) -> None:
        self.mini_btn.setText(self._mini_button_label())

    def _on_mini_toggle(self) -> None:
        # If already running, kill it.
        if self._mini_proc is not None and self._mini_proc.poll() is None:
            self.logger.info("closing mini window (pid=%d)",
                             self._mini_proc.pid)
            self._mini_proc.terminate()
            try:
                self._mini_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._mini_proc.kill()
            self._mini_proc = None
            self._refresh_mini_button()
            return
        # Pick the first skin (operator-curated picker lands in
        # Settings page later).  Fall back to launching with no skin,
        # which uses the launcher's own DEFAULT_IMAGE.
        skin = None
        if self._available_skins:
            skin = Path(self._available_skins[0]["_path"])
        self._mini_proc = launch_mini_window(skin, self.logger)
        self._refresh_mini_button()
        # Poll once a second for the subprocess exiting so the button
        # label catches up.
        QTimer.singleShot(1500, self._poll_mini_status)

    def _poll_mini_status(self) -> None:
        if self._mini_proc is not None and self._mini_proc.poll() is not None:
            # Process exited externally — reset state.
            self.logger.info("mini window exited externally")
            self._mini_proc = None
            self._refresh_mini_button()
            return
        if self._mini_proc is not None:
            QTimer.singleShot(1500, self._poll_mini_status)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Clean up the subprocess on companion close.
        if self._mini_proc is not None and self._mini_proc.poll() is None:
            self._mini_proc.terminate()
            try:
                self._mini_proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self._mini_proc.kill()
        # Stop the HealthService background thread cleanly.
        if hasattr(self, "health"):
            try:
                self.health.stop()
            except Exception:  # noqa: BLE001
                pass
        # Terminate any editor subprocesses spawned from Editors tab.
        editors = self.pages.get("Editors")
        if isinstance(editors, EditorsPage):
            editors.cleanup_subprocesses()
        super().closeEvent(event)


# ── entry point ────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ctrl-addr", default=DEFAULT_CTRL_ADDR,
        help=f"Animation node ctrl PUSH endpoint "
             f"(default: {DEFAULT_CTRL_ADDR})",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-18s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Goodbye Tk — Phase 6 of docs/SUPERSEDE_TK_PLAN.md.  The Tk
    # debug panel (gui/mochi_gui.py) is disabled by default in
    # config.yaml as of this commit.  This log line is the
    # provenance marker.
    logging.getLogger("MochiCompanion").info(
        "Mochi Companion — supersedes the legacy Tk panel "
        "(see docs/SUPERSEDE_TK_PLAN.md for the migration plan)."
    )

    app = QApplication(sys.argv)
    app.setFont(QFont("-apple-system", 13))

    win = CompanionMain(args.ctrl_addr)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
