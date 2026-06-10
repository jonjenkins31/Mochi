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
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QStackedWidget, QListWidget, QListWidgetItem,
    QScrollArea, QSizePolicy, QSpacerItem,
    QTextBrowser, QSplitter,
)

import zmq

GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
CATALOG_PATH = PROJECT_ROOT / "assets" / "CATALOG.json"
PACKS_DIR    = PROJECT_ROOT / "assets" / "packs"
SKINS_DIR    = PROJECT_ROOT / "assets" / "skins"
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
QPushButton.sidebar_btn {{
    background: transparent;
    color: {TEXT_MAIN};
    text-align: left;
    padding: 10px 20px;
    border: none;
    border-radius: 8px;
    margin: 2px 8px;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton.sidebar_btn:hover {{
    background: {ACCENT_BG};
}}
QPushButton.sidebar_btn:checked {{
    background: {ACCENT_BG};
    color: {ACCENT_DARK};
    font-weight: 600;
}}

/* Top bar */
#topbar {{
    background: {BG_BASE};
    border-bottom: 1px solid {BORDER};
}}
#page_title {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT_MAIN};
}}

QPushButton.tab_btn {{
    background: transparent;
    color: {TEXT_MUTED};
    border: none;
    padding: 10px 14px;
    margin-right: 4px;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton.tab_btn:hover {{
    color: {TEXT_MAIN};
}}
QPushButton.tab_btn:checked {{
    color: {ACCENT_DARK};
    border-bottom: 2px solid {ACCENT_DARK};
    font-weight: 600;
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


def make_card(entry: dict, on_click) -> QFrame:
    """One catalog entry as a clickable card."""
    card = QFrame()
    card.setObjectName("card")
    card.setProperty("class", "card")
    card.setCursor(Qt.PointingHandCursor)
    card.setFixedSize(220, 200)
    card.mousePressEvent = lambda _e: on_click(entry)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    # Preview tile — first letter for now, will become thumbnail later
    preview = QLabel(entry["name"][:1].upper())
    preview.setAlignment(Qt.AlignCenter)
    preview.setProperty("class", "card_preview")
    preview.setStyleSheet(f"""
        background: {ACCENT_BG};
        color: {ACCENT_DARK};
        border-radius: 6px;
        font-size: 40px;
        font-weight: 700;
        min-height: 90px;
    """)
    layout.addWidget(preview)

    title = QLabel(entry["name"])
    title.setProperty("class", "card_title")
    title.setStyleSheet(
        f"color: {TEXT_MAIN}; font-size: 13px; font-weight: 600;"
    )
    title.setWordWrap(True)
    layout.addWidget(title)

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

        outer.addWidget(self._build_filter_row(
            "Mood", moods, self._mood_buttons, self._select_mood,
        ))
        outer.addWidget(self._build_filter_row(
            "Type", types, self._type_buttons, self._select_type,
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

    def _filtered(self) -> list[dict]:
        results = []
        for e in self.entries:
            if (self._current_mood != "all"
                    and e.get("mood") != self._current_mood):
                continue
            if (self._current_type != "all"
                    and e.get("type") != self._current_type):
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

        For now we always emit ``node animation mode <name>``.  Later
        commits (when scene + reaction pools land) can route mscript
        entries to play <path> instead.
        """
        name = entry.get("name", "")
        type_ = entry.get("type", "")
        if type_ == "mscripts":
            path = entry.get("path", "")
            self.ctrl.send(f"play {path}")
        else:
            self.ctrl.send(f"node animation mode on {name}")


class PacksPage(QWidget):
    """Pack browser — top-level character/style selection.

    Empty state when ``assets/packs/`` has no pack.yaml files yet
    (operator note 2026-06-10: "most stuff are one-offs... I am
    working on the packs").  As packs land, this page populates with
    pack cards; click → emotion-slot view (TODO when first pack exists).
    """

    def __init__(self, ctrl: CtrlBridge, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.ctrl = ctrl

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── top bar ───────────────────────────────────────────────
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(28, 22, 28, 16)
        title = QLabel("Packs")
        title.setObjectName("page_title")
        topbar_layout.addWidget(title)
        topbar_layout.addStretch()
        outer.addWidget(topbar)

        # ── content area ──────────────────────────────────────────
        content = QFrame()
        content.setStyleSheet(f"background: {BG_BASE};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 20, 28, 28)
        content_layout.setSpacing(16)

        packs = discover_packs()
        if not packs:
            content_layout.addSpacing(40)
            heading = QLabel("No packs yet")
            heading.setStyleSheet(
                f"color: {TEXT_MAIN}; font-size: 20px; "
                f"font-weight: 600;"
            )
            heading.setAlignment(Qt.AlignHCenter)
            content_layout.addWidget(heading)

            content_layout.addSpacing(12)
            sub = QLabel(
                "Most of the current assets are one-offs (browse them on "
                "the Library tab).\n\nWhen you add a pack folder under "
                "<code>assets/packs/&lt;id&gt;/</code> with a "
                "<code>pack.yaml</code>, it appears here.\n\n"
                "See <code>docs/PACK_CONVENTION.md</code> for the format."
            )
            sub.setTextFormat(Qt.RichText)
            sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
            sub.setAlignment(Qt.AlignHCenter)
            sub.setWordWrap(True)
            sub.setMaximumWidth(600)
            container = QHBoxLayout()
            container.addStretch()
            container.addWidget(sub)
            container.addStretch()
            content_layout.addLayout(container)
            content_layout.addStretch()
        else:
            # Pack cards — first version is name + slot count.  When a
            # real pack exists with preview_slot, swap to thumbnails.
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(16)
            grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            for i, pack in enumerate(packs):
                card = self._make_pack_card(pack)
                r, c = divmod(i, 4)
                grid.addWidget(card, r, c)
            content_layout.addLayout(grid)
            content_layout.addStretch()

        outer.addWidget(content)

    def _make_pack_card(self, pack: dict) -> QFrame:
        card = QFrame()
        card.setProperty("class", "card")
        card.setObjectName("card")
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedSize(240, 220)
        card.mousePressEvent = lambda _e, p=pack: self._on_pack_click(p)

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

        title = QLabel(pack.get("name", pack.get("id", "?")))
        title.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 14px; font-weight: 600;"
        )
        layout.addWidget(title)

        slots = pack.get("slots", {}) or {}
        slot_count = len(slots) if isinstance(slots, dict) else 0
        author = pack.get("author", "")
        meta = QLabel(f"{slot_count} slots  ·  {author}")
        meta.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(meta)

        return card

    def _on_pack_click(self, pack: dict) -> None:
        # Pack detail view lands in a follow-up commit when we have a
        # real pack to design against.  For now, log + fire the pack's
        # default slot if one is defined.
        default_slot = pack.get("default_slot")
        slots = pack.get("slots", {}) or {}
        if default_slot and default_slot in slots:
            slot_file = slots[default_slot]
            if isinstance(slot_file, list):
                slot_file = slot_file[0] if slot_file else None
            if slot_file:
                # Use the bare filename; the animation node's existing
                # mode resolver picks it up via the catalog or its own
                # animations/__init__.py registration.
                stem = Path(str(slot_file)).stem
                self.ctrl.send(f"node animation mode on {stem}")


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


class StubPage(QWidget):
    """Placeholder for tabs not yet wired (Home, Scenes, Triggers,
    Schedule, Editors, Settings)."""

    def __init__(self, title: str, phase: str, hint: str,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(8)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(0, 0, 0, 16)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("page_title")
        topbar_layout.addWidget(title_lbl)
        topbar_layout.addStretch()
        layout.addWidget(topbar)

        layout.addSpacing(40)
        heading = QLabel(f"{title} — coming in {phase}")
        heading.setProperty("class", "coming_soon_heading")
        heading.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 20px; font-weight: 600;"
        )
        heading.setAlignment(Qt.AlignHCenter)
        layout.addWidget(heading)

        layout.addSpacing(12)
        sub = QLabel(hint)
        sub.setProperty("class", "coming_soon")
        sub.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 13px;"
        )
        sub.setAlignment(Qt.AlignHCenter)
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addStretch()


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

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo = QLabel("MOCHI")
        logo.setObjectName("sidebar_logo")
        layout.addWidget(logo)

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

        layout.addStretch()

        # Bottom promo / nudge — empty for now but reserves the space
        nudge = QLabel(
            "Mochi v3 alpha\n"
            "167 animations indexed"
        )
        nudge.setStyleSheet(
            f"background: {ACCENT_BG}; color: {ACCENT_DARK}; "
            f"border-radius: 8px; padding: 14px; margin: 16px; "
            f"font-size: 11px; font-weight: 500;"
        )
        nudge.setAlignment(Qt.AlignCenter)
        layout.addWidget(nudge)

    def _select(self, label: str) -> None:
        for l, btn in self._buttons.items():
            btn.setChecked(l == label)
        self.item_selected.emit(label)

    def select_default(self, label: str = "Library") -> None:
        if label in self._buttons:
            self._buttons[label].click()


# ── main window ────────────────────────────────────────────────────

class CompanionMain(QMainWindow):
    def __init__(self, ctrl_addr: str) -> None:
        super().__init__()
        self.logger = logging.getLogger("MochiCompanion")
        self.setWindowTitle("Mochi Companion")
        self.resize(1280, 820)
        self.setStyleSheet(STYLESHEET)

        self.ctrl = CtrlBridge(ctrl_addr, self.logger)
        self._mini_proc: subprocess.Popen | None = None
        self._available_skins: list[dict] = discover_skins()

        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.item_selected.connect(self._on_sidebar_select)
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
        toolbar_layout.addStretch()
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
        self.pages["Home"] = StubPage(
            "Home", "Phase B",
            "Scene wheel + favorites + animation grid + reaction "
            "button row + personality slider.  Pick a scene; the "
            "character does the rest.",
        )
        self.pages["Library"] = LibraryPage(self.ctrl)
        self.pages["Packs"] = PacksPage(self.ctrl)
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
        self.pages["Editors"] = StubPage(
            "Editors", "Phase A.4",
            "In-app sprite / bitmap / mscript editor.  Existing "
            "tools/*_editor_gui.py surfaces folded in here.",
        )
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

    def _build_settings_page(self) -> QWidget:
        """Minimal Settings — lists discovered skins.  Picker UI lands
        when the operator has > 1 skin to choose between."""
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
        outer.addWidget(topbar)

        body = QFrame()
        body.setStyleSheet(f"background: {BG_BASE};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 20, 28, 28)
        body_layout.setSpacing(12)

        heading = QLabel("Skins")
        heading.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 16px; font-weight: 600;"
        )
        body_layout.addWidget(heading)

        sub = QLabel(
            "Body frames the mini window wears.  Drop folders under "
            "<code>assets/skins/&lt;id&gt;/</code> with "
            "<code>body.png</code> + <code>meta.yaml</code>.  See "
            "<code>docs/SKIN_CONVENTION.md</code>."
        )
        sub.setTextFormat(Qt.RichText)
        sub.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        sub.setWordWrap(True)
        body_layout.addWidget(sub)

        if not self._available_skins:
            empty = QLabel("(no skins detected)")
            empty.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 13px; "
                f"padding: 12px 0;"
            )
            body_layout.addWidget(empty)
        else:
            for skin in self._available_skins:
                row = QFrame()
                row.setProperty("class", "card")
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
                author = skin.get("author")
                if author:
                    meta_bits.append(f"by {author}")
                if skin.get("_warning"):
                    meta_bits.append(f"⚠ {skin['_warning']}")
                meta = QLabel("  ·  ".join(meta_bits))
                meta.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-size: 12px;"
                )
                rl.addWidget(meta)
                rl.addStretch()
                body_layout.addWidget(row)

        body_layout.addStretch()
        outer.addWidget(body)
        return page

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

    app = QApplication(sys.argv)
    app.setFont(QFont("-apple-system", 13))

    win = CompanionMain(args.ctrl_addr)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
