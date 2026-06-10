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
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFrame,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QStackedWidget, QListWidget, QListWidgetItem,
    QScrollArea, QSizePolicy, QSpacerItem,
)

import zmq

GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
CATALOG_PATH = PROJECT_ROOT / "assets" / "CATALOG.json"
PACKS_DIR    = PROJECT_ROOT / "assets" / "packs"

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

        # ── filter chips (mood) ───────────────────────────────────
        chip_row = QFrame()
        chip_row.setStyleSheet(
            f"background: {BG_BASE}; "
            f"border-bottom: 1px solid {BORDER};"
        )
        chip_layout = QHBoxLayout(chip_row)
        chip_layout.setContentsMargins(28, 0, 28, 0)
        chip_layout.setSpacing(0)
        moods = ["all"] + sorted(
            {e.get("mood", "neutral") for e in self.entries}
        )
        self._mood_buttons: dict[str, QPushButton] = {}
        for mood in moods:
            btn = QPushButton(mood.upper())
            btn.setProperty("class", "tab_btn")
            btn.setCheckable(True)
            if mood == "all":
                btn.setChecked(True)
            btn.clicked.connect(
                lambda _checked=False, m=mood: self._select_mood(m)
            )
            self._mood_buttons[mood] = btn
            chip_layout.addWidget(btn)
        chip_layout.addStretch()
        outer.addWidget(chip_row)

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

    # ── filtering ─────────────────────────────────────────────────

    def _on_search(self, text: str) -> None:
        self._search_text = text.lower().strip()
        self._rebuild_grid()

    def _select_mood(self, mood: str) -> None:
        # Mutual-exclusive toggle group
        for m, btn in self._mood_buttons.items():
            btn.setChecked(m == mood)
        self._current_mood = mood
        self._rebuild_grid()

    def _filtered(self) -> list[dict]:
        results = []
        for e in self.entries:
            if (self._current_mood != "all"
                    and e.get("mood") != self._current_mood):
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

        central = QWidget()
        self.setCentralWidget(central)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.item_selected.connect(self._on_sidebar_select)
        h.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)

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
        self.pages["Settings"] = StubPage(
            "Settings", "Phase C",
            "Skin picker (TV bezel + custom body frames), "
            "personality dial, LLM mode toggle, broker addresses.",
        )

        for name, page in self.pages.items():
            self.stack.addWidget(page)

        self.sidebar.select_default("Library")

    def _on_sidebar_select(self, label: str) -> None:
        page = self.pages.get(label)
        if page is not None:
            self.stack.setCurrentWidget(page)


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
