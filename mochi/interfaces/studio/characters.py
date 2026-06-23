"""Characters page — the library list + a JANE-style profile.

Embedded as the Studio "Characters" tab. Reads the character library
(``personality/characters/``) and renders the selected character's sheet: name,
the SPECIAL attributes as bars, the Domains as PROGRESS levels, and the
prompt the model sees today. Pure view over :mod:`mochi.personality.character`.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from mochi.interfaces.studio.window import (
    ACCENT, BG, GOOD, INK, INK_DIM, PANEL, PANEL_HI, STROKE, _label,
)
from mochi.personality.character import Character, layer_items, list_characters


def _bar(value: float, color: str = GOOD) -> QProgressBar:
    p = QProgressBar()
    p.setRange(0, 100)
    p.setValue(int(round(_f(value) * 100)))
    p.setTextVisible(False)
    p.setFixedHeight(8)
    p.setStyleSheet(
        f"QProgressBar{{background:{STROKE};border:none;border-radius:4px;}}"
        f"QProgressBar::chunk{{background:{color};border-radius:4px;}}")
    return p


def _f(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


class CharactersPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._chars: list[Character] = list_characters()
        self._active_id = self._read_active()
        self._build()

    def _read_active(self) -> str:
        try:
            from mochi.core.instance.instance import resolve_instance_dir
            from mochi.personality.character import active_character_id
            return active_character_id(resolve_instance_dir())
        except Exception:  # noqa: BLE001
            return ""

    def _use(self, c: Character) -> None:
        try:
            from mochi.core.instance.instance import resolve_instance_dir
            from mochi.personality.character import set_active_character
            set_active_character(resolve_instance_dir(), c.id)
            self._active_id = c.id
        except Exception:  # noqa: BLE001
            pass
        self._show(self._list.currentRow())

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # ── library list ──────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_label("Character Library", size=14, bold=True))
        head.addStretch(1)
        head.addWidget(_label(f"{len(self._chars)}", color=INK_DIM, size=12))
        left.addLayout(head)
        self._list = QListWidget()
        self._list.setObjectName("Library")
        self._list.setFixedWidth(230)
        for c in self._chars:
            self._list.addItem(f"  {c.name}")
        self._list.currentRowChanged.connect(self._show)
        left.addWidget(self._list, stretch=1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(230)
        root.addWidget(lw)

        # ── profile (rebuilt per selection) ───────────────────────
        self._profile = QFrame()
        self._profile.setObjectName("Stage")
        self._profile_lay = QVBoxLayout(self._profile)
        self._profile_lay.setContentsMargins(24, 22, 24, 22)
        self._profile_lay.setSpacing(16)
        root.addWidget(self._profile, stretch=1)

        if self._chars:
            self._list.setCurrentRow(0)
        else:
            self._profile_lay.addWidget(_label("No characters found.", color=INK_DIM))

    # ── profile render ────────────────────────────────────────────
    def _show(self, idx: int) -> None:
        while self._profile_lay.count():
            item = self._profile_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not (0 <= idx < len(self._chars)):
            return
        c = self._chars[idx]

        # header — big name + role
        name = _label(c.name, size=30, bold=True)
        self._profile_lay.addWidget(name)
        if c.role or c.description:
            self._profile_lay.addWidget(_label(c.role or c.description, color=INK_DIM, size=13))

        # select this character for the agent
        act = QHBoxLayout()
        use = QPushButton("✦  Use this character")
        use.setObjectName("Tab" if c.id == self._active_id else "Accent")
        use.setCursor(Qt.CursorShape.PointingHandCursor)
        use.clicked.connect(lambda: self._use(c))
        act.addWidget(use)
        if c.id == self._active_id:
            act.addWidget(_label("● ACTIVE — the agent is playing this character",
                                 color=GOOD, size=12, bold=True))
        act.addStretch(1)
        aw = QWidget(); aw.setLayout(act)
        self._profile_lay.addWidget(aw)

        # body: ATTRIBUTES | portrait | PROGRESS
        body = QHBoxLayout()
        body.setSpacing(22)
        body.addLayout(self._attrs(c), stretch=1)
        body.addWidget(self._portrait(c))
        body.addLayout(self._progress(c), stretch=1)
        bw = QWidget()
        bw.setLayout(body)
        self._profile_lay.addWidget(bw, stretch=1)

        # prompt the model sees today
        self._profile_lay.addWidget(_label("CHARACTER PROMPT (what the model sees today)",
                                            color=INK_DIM, size=10, bold=True))
        prompt = QLabel(c.prompt() or "—")
        prompt.setWordWrap(True)
        prompt.setStyleSheet(f"color:{INK}; background:{PANEL_HI}; border-radius:10px; padding:12px;")
        self._profile_lay.addWidget(prompt)

    def _attrs(self, c: Character) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(10)
        col.addWidget(_label("ATTRIBUTES", color=INK_DIM, size=11, bold=True))
        for key, val in layer_items(c.personality.special):
            col.addWidget(_label(key.upper(), color=INK, size=12))
            col.addWidget(_bar(val))
        col.addStretch(1)
        return col

    def _progress(self, c: Character) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        col.addWidget(_label("PROGRESS", color=INK_DIM, size=11, bold=True))
        for key, val in layer_items(c.personality.domains):
            row = QHBoxLayout()
            row.addWidget(_label(key.upper(), color=INK, size=12))
            row.addStretch(1)
            row.addWidget(_label(f"LVL {int(round(_f(val) * 15))}", color=GOOD, size=12, bold=True))
            col.addLayout(row)
            col.addWidget(_bar(val))
        col.addStretch(1)
        return col

    def _portrait(self, c: Character) -> QWidget:
        box = QFrame()
        box.setObjectName("Stage")
        box.setFixedWidth(220)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        lab = QLabel()
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = c.card_path()
        if card is not None:
            lab.setPixmap(QPixmap(str(card)).scaledToWidth(
                200, Qt.TransformationMode.SmoothTransformation))
        else:
            lab.setText("◍")
            lab.setStyleSheet(f"color:{INK_DIM}; font-size:64px;")
        v.addWidget(lab)
        return box
