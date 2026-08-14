"""The roster, as cards you can pick.

A character is a folder, and a folder is hard to browse. A dropdown of
names tells you a pack called "bitmap man" exists; a card tells you what
it looks like, which is the thing you were actually choosing between.
JaegerAI ships a 320×420 card per character for exactly this reason, and
this is the same idea pointed at the packs that also have a face.

EVERY PACK GETS A TILE, whether or not anyone drew it one:

    card: in character.yaml     an authored card, the best case
    card.png beside it          the convention, no manifest edit needed
    the pack's render asset     what it actually looks like on screen
    its name on a plain tile    still selectable, still honest

The fallback chain matters more than it looks. Most packs here have no
card and are never going to get one, and a roster where half the entries
are blank rectangles is worse than no roster — so the third rung reuses
the art the pack already has, and only a pack whose art Qt cannot decode
(video clips) lands on a name.

Selecting is a callback rather than a signal so this widget owns no
state: the Face tab keeps the live character, and this tells it when to
change. Two views, one truth — the same rule the audio switches follow.
"""

from __future__ import annotations

import pathlib
from typing import Any, Callable

import yaml

from PySide6 import QtCore, QtGui, QtWidgets

CARD_W, CARD_H = 104, 136


def card_for(root: pathlib.Path) -> pathlib.Path | None:
    """The image that best represents this pack, or None for a name tile."""
    root = pathlib.Path(root)
    try:
        sheet = yaml.safe_load(
            (root / "character.yaml").read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — a broken pack is the renderer's to report
        sheet = {}

    declared = str(sheet.get("card") or "").strip()
    if declared and (root / declared).is_file():
        return root / declared
    if (root / "card.png").is_file():
        return root / "card.png"

    # Whatever it renders is a truer thumbnail than a placeholder. Only
    # still images qualify — a video clip needs a decoder, and decoding
    # is the engine's job, not a tab's.
    render = dict(sheet.get("render") or {})
    asset = str(render.get("asset") or "").strip()
    if asset and (root / asset).is_file() and (root / asset).suffix.lower() in (
            ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
        return root / asset
    return None


class CharacterCards(QtWidgets.QWidget):
    """A scrollable strip of character cards, one selected at a time."""

    def __init__(self, entries: list[tuple[str, str, pathlib.Path]],
                 on_pick: Callable[[str], None]) -> None:
        """`entries` is (id, label, folder) per character.

        The ID is what everything else calls this character — the same
        string the pack dropdown and `animation.load()` use — and it is
        deliberately NOT the folder name, which is a display convention
        ("Cyber Cat" is the pack `cat`). Keying cards on the folder is
        how the strip and the dropdown ended up unable to select each
        other's choices.

        Discovery belongs to the caller for the same reason: the module
        already answers "which characters exist", and a second answer
        computed from the filesystem is a second answer that can differ.
        """
        super().__init__()
        self._entries = list(entries)
        self._on_pick = on_pick
        self._buttons: dict[str, QtWidgets.QToolButton] = {}

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        # Tall enough for a card, its label, AND the horizontal scrollbar.
        # Sized off the button rather than guessed, because leaving the
        # scrollbar out of the sum is what clipped every label.
        scroll.setFixedHeight(CARD_H + 38 + 22)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        strip = QtWidgets.QWidget()
        self.row = QtWidgets.QHBoxLayout(strip)
        self.row.setContentsMargins(2, 2, 2, 2)
        self.row.setSpacing(8)
        scroll.setWidget(strip)
        outer.addWidget(scroll)
        self.reload()

    # ── building ─────────────────────────────────────────────────

    def reload(self) -> None:
        """Rebuild the strip from the entries handed in."""
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons = {}
        for identifier, label, folder in self._entries:
            button = self._card_button(identifier, label, folder)
            self._buttons[identifier] = button
            self.row.addWidget(button)
        self.row.addStretch(1)

    def _card_button(self, identifier: str, label: str,
                     folder: pathlib.Path) -> QtWidgets.QToolButton:
        button = QtWidgets.QToolButton()
        button.setCheckable(True)
        button.setAutoExclusive(True)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        button.setIconSize(QtCore.QSize(CARD_W, CARD_H))
        button.setFixedSize(CARD_W + 16, CARD_H + 38)
        button.setText(label)
        button.setToolTip(f"{label}  ({identifier})")
        button.setStyleSheet(
            "QToolButton { background:#16161c; border:1px solid #2a2a34;"
            " border-radius:6px; padding:4px; font-size:10px; }"
            "QToolButton:hover { border-color:#4a7ab0; }"
            "QToolButton:checked { border:2px solid #4a7ab0; background:#1e2634; }")

        art = card_for(folder)
        if art is not None:
            pixmap = QtGui.QPixmap(str(art))
            if not pixmap.isNull():
                button.setIcon(QtGui.QIcon(pixmap.scaled(
                    CARD_W, CARD_H, QtCore.Qt.KeepAspectRatioByExpanding,
                    QtCore.Qt.SmoothTransformation)))
        button.clicked.connect(
            lambda _checked=False, name=identifier: self._on_pick(name))
        return button

    # ── staying in sync ──────────────────────────────────────────

    def select(self, name: str) -> None:
        """Show `name` as current without calling back.

        The character can change from the dropdown beside this strip, so
        the cards read their position from whoever owns the truth rather
        than remembering the last click.
        """
        button = self._buttons.get(name)
        if button is None or button.isChecked():
            return
        button.blockSignals(True)
        button.setChecked(True)
        button.blockSignals(False)


__all__ = ["CharacterCards", "card_for", "CARD_W", "CARD_H"]
