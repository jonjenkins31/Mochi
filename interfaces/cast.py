"""The Cast tab — pick who the agent is, from cards you can actually read.

A dropdown tells you a pack called "bitmap man" exists. A card shows you
what it looks like, what it is, and how it talks, which is what you were
choosing between. JaegerAI's character library does this with a big
art-filled card per character and the actions on the card itself; that
design is the reason this tab looks the way it does. None of its code is
here — Mochi's packs are folders with a `character.yaml`, not JaegerAI
personalities, and everything below reads Mochi's own sheet.

WHAT A CARD SHOWS, and where each line comes from:

    art       card:  in character.yaml, else card.png, else its render
              asset — the same chain the Face tab's strip already uses
    name      the pack's display name
    role      identity.role, the one line that says what it IS
    voice     identity.voice_tone, because a character is a face AND a
              voice and picking one picks both

PIXEL ART IS NOT PHOTOGRAPHY. JaegerAI's card fills its frame by
expanding a 320×420 portrait. Mochi's `bitmap man` renders 72×32, and
expanding that to fill a card is a smear. So art at least as large as
the card fills it, and anything smaller is drawn centred at a whole-
number zoom with nearest-neighbour — the same rule the display honours.

SELECTING IS NOT OWNING. The card calls back; the Face tab keeps the
live character and remains the only place a pack is loaded. Two views,
one truth — and it is why picking here changes the avatar window too,
without this file knowing that window exists.
"""

from __future__ import annotations

import pathlib
from typing import Any, Callable

import yaml
from PySide6 import QtCore, QtGui, QtWidgets

from .character_cards import card_for

CARD_W, CARD_H = 244, 316


def _sheet(root: pathlib.Path) -> dict:
    try:
        data = yaml.safe_load(
            (root / "character.yaml").read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — a broken pack still gets a tile
        return {}
    return data if isinstance(data, dict) else {}


class RosterCard(QtWidgets.QFrame):
    """One character: its art, what it is, and the two things you can do."""

    def __init__(self, identifier: str, label: str, root: pathlib.Path,
                 on_select: Callable[[str], None]) -> None:
        super().__init__()
        self.identifier = identifier
        self._active = False
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(QtCore.Qt.PointingHandCursor)

        art = card_for(root)
        self._art = QtGui.QPixmap(str(art)) if art else QtGui.QPixmap()
        sheet = _sheet(root)
        identity = dict(sheet.get("identity") or {})

        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(14, 12, 14, 14)
        column.setSpacing(2)
        column.addStretch(1)

        name = QtWidgets.QLabel((label or identifier).upper())
        name.setStyleSheet("color:#f0eef7;font-size:17px;font-weight:800;")
        column.addWidget(name)

        role = QtWidgets.QLabel(str(identity.get("role")
                                    or sheet.get("description") or "—"))
        role.setStyleSheet("color:#C9C4E0;font-size:11px;")
        role.setWordWrap(True)
        role.setMaximumHeight(46)
        column.addWidget(role)

        tone = str(identity.get("voice_tone") or "").strip()
        if tone:
            voice = QtWidgets.QLabel(f"voice · {tone}")
            voice.setStyleSheet("color:#8A85A6;font-size:10px;")
            voice.setWordWrap(True)
            voice.setMaximumHeight(28)
            column.addWidget(voice)
        column.addSpacing(8)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)
        self.select = QtWidgets.QPushButton("SELECT")
        self.select.setObjectName("Select")
        self.select.setCursor(QtCore.Qt.PointingHandCursor)
        self.select.clicked.connect(lambda: on_select(identifier))
        # Editing a pack is the Characters tab's job and it already does
        # it. A second editor entry point that opens nothing is worse
        # than a button that says what it is: not wired up yet.
        self.edit = QtWidgets.QPushButton("EDIT")
        self.edit.setObjectName("Edit")
        self.edit.setEnabled(False)
        self.edit.setToolTip("not wired up — edit packs on the Characters tab")
        buttons.addWidget(self.select, 3)
        buttons.addWidget(self.edit, 2)
        column.addLayout(buttons)
        self._restyle()

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            self._restyle()
            self.update()

    def _restyle(self) -> None:
        self.select.setText("✓ ACTIVE" if self._active else "SELECT")
        self.select.setEnabled(not self._active)
        self.setStyleSheet(
            "QPushButton#Select{background:%s;color:%s;border:none;"
            "border-radius:8px;padding:8px;font-weight:800;font-size:11px;}"
            "QPushButton#Select:disabled{background:#6C5CE7;color:#ffffff;}"
            "QPushButton#Edit{background:#1B1630;color:#8A85A6;"
            "border:1px solid #2A2340;border-radius:8px;padding:8px;"
            "font-weight:800;font-size:11px;}"
            % (("#6C5CE7", "#ffffff") if self._active
               else ("#241D3D", "#e8e6f0")))

    def paintEvent(self, event: Any) -> None:  # noqa: N802 — Qt override
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        box = QtCore.QRectF(self.rect().adjusted(0, 0, -1, -1))
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(box, 14, 14)
        painter.setClipPath(clip)
        painter.fillRect(box, QtGui.QColor("#141021"))
        self._paint_art(painter)

        # The text sits on the art, so the art has to fade out under it.
        fade = QtGui.QLinearGradient(0, self.height() * 0.30, 0, self.height())
        fade.setColorAt(0.0, QtGui.QColor(11, 9, 16, 0))
        fade.setColorAt(0.55, QtGui.QColor(11, 9, 16, 205))
        fade.setColorAt(1.0, QtGui.QColor(11, 9, 16, 246))
        painter.fillRect(box, QtGui.QBrush(fade))

        painter.setClipping(False)
        painter.setPen(QtGui.QPen(
            QtGui.QColor("#6C5CE7" if self._active else "#2A2340"),
            2 if self._active else 1))
        painter.drawRoundedRect(box, 14, 14)
        painter.end()

    def _paint_art(self, painter: QtGui.QPainter) -> None:
        if self._art.isNull():
            return
        big = (self._art.width() >= CARD_W or self._art.height() >= CARD_H)
        if big:
            # Smoothing is right when shrinking a photograph and wrong
            # when enlarging anything — and a 256x256 render enlarged to
            # fill this card is enlarging. Decide by direction, not by
            # guessing what kind of picture it is.
            grows = (self._art.width() < self.width()
                     or self._art.height() < self.height())
            scaled = self._art.scaled(
                self.size(), QtCore.Qt.KeepAspectRatioByExpanding,
                QtCore.Qt.FastTransformation if grows
                else QtCore.Qt.SmoothTransformation)
            painter.drawPixmap(
                0, 0, scaled, max(0, (scaled.width() - self.width()) // 2),
                max(0, (scaled.height() - self.height()) // 2),
                self.width(), self.height())
            return
        # Small art is pixel art. Whole-number zoom, nearest neighbour,
        # sat in the upper part of the card where the gradient is clear.
        zoom = max(1, min(int(CARD_W * 0.72) // max(1, self._art.width()),
                          int(CARD_H * 0.55) // max(1, self._art.height())))
        scaled = self._art.scaled(self._art.width() * zoom,
                                  self._art.height() * zoom,
                                  QtCore.Qt.KeepAspectRatio,
                                  QtCore.Qt.FastTransformation)
        painter.drawPixmap((self.width() - scaled.width()) // 2,
                           int(CARD_H * 0.30) - scaled.height() // 2, scaled)


class CastTab:
    """Every installed character, as cards. Picking one switches the app."""

    def __init__(self, app: Any, qt: tuple, entries: list,
                 on_select: Callable[[str], None], active: str = "") -> None:
        _QtCore, _QtGui, QtWidgets_ = qt
        self.cards: dict[str, RosterCard] = {}

        self.widget = QtWidgets_.QWidget()
        outer = QtWidgets_.QVBoxLayout(self.widget)
        outer.setContentsMargins(10, 10, 10, 10)
        note = QtWidgets_.QLabel(
            "Who the agent is. Selecting switches the face, the voice and "
            "the persona together — everywhere, including the avatar window.")
        note.setStyleSheet("color:#777784;")
        outer.addWidget(note)

        scroll = QtWidgets_.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets_.QFrame.NoFrame)
        holder = QtWidgets_.QWidget()
        self.grid = QtWidgets_.QGridLayout(holder)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(12)
        self.grid.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        for index, (identifier, label, root) in enumerate(entries):
            card = RosterCard(identifier, label, pathlib.Path(root), on_select)
            self.cards[identifier] = card
            self.grid.addWidget(card, index // 4, index % 4)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)
        if active:
            self.set_active(active)

    def set_active(self, identifier: str) -> None:
        """Reflect whoever is live. Called when the pack changes from
        ANYWHERE — this tab is a view of that fact, not its owner."""
        for name, card in self.cards.items():
            card.set_active(name == identifier)

    def close(self) -> None:
        """No timers and no subscriptions: a card is paint and a click."""


__all__ = ["CastTab", "RosterCard", "CARD_W", "CARD_H"]
