"""Face tab — a subscriber that happens to have pixels in it.

    /act/display/play  ◀── controls
    /act/display/frame ──▶ PlayerWindow

That is the whole contract. The window does not call the animation
engine, does not know which adapter is running, and does not import
anything from it. It receives RGBA frames on a topic and blits them.

Which is why the same engine drives an LED matrix and JP01's face:
they are different subscribers, not different code paths. If this file
ever imports `jaeger_animation`, that property is gone.

The reverse direction is just as thin. To change what is showing,
Mochi publishes a DisplayCommand — asset, adapter, params — and the
engine decides what that means. Mochi never sends "be happy"; it sends
"cell 6 of this atlas", having looked up what "happy" means in the
CHARACTER's own vocabulary.

**Any file plays.** The engine ships adapters for image, gif, video,
sprite, bitmap and mscript, and picks one from the extension when the
command says ``adapter="auto"``. So "open a file" needs no adapter
knowledge here at all — which is exactly what a player should be.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any


from jaeger_os import topics

from modules import animation

_FRAME = topics.ACT_DISPLAY_FRAME
_STATE = topics.ACT_DISPLAY_STATE

#: Files the open dialog offers. Mirrors the adapters the animation
#: module ships; anything else still plays if the engine knows it,
#: this list only shapes the dialog.
_FILE_FILTER = (
    "Playable (*.gif *.png *.jpg *.jpeg *.bmp *.mp4 *.mov *.mscript *.py);;"
    "Images (*.png *.jpg *.jpeg *.bmp);;"
    "Animations (*.gif);;"
    "Video (*.mp4 *.mov);;"
    "Procedural (*.mscript *.py);;"
    "All files (*)"
)


class FaceTab:
    """Shows whatever is on ``/act/display/frame``, and drives it."""

    def __init__(self, app: Any, qt: tuple, config: dict[str, Any]) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui, self._QtWidgets = QtCore, QtGui, QtWidgets

        self.bus = app.bus
        self.scale = int(os.environ.get("MOCHI_SCALE", config.get("scale", 2)))
        self.dwell_ms = int(float(config.get("dwell_s", 1.5)) * 1000)
        self.character = animation.load(
            os.environ.get("MOCHI_CHARACTER", config.get("character", "emotes")))
        # The pack's own vocabulary, in declaration order — the order a
        # character author chose is more useful than alphabetical.
        self._expressions = list(self.character.expressions)

        self._frame = None            # QImage; written by the bus thread
        self._status_text: str | None = None   # ditto — drained on repaint
        self._expression_idx = 0
        self._mouth = self.character.default_mouth
        self._playing_asset: pathlib.Path | None = None

        self._build_ui()
        self.bus.subscribe(_FRAME, self._on_frame)
        self.bus.subscribe(_STATE, self._on_state)

        # Repaint on the GUI thread, never from a bus callback. Qt
        # widgets are not thread-safe, and a subscriber runs on the
        # bus's delivery thread — touching a widget there is a crash
        # that only shows up under load.
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._repaint)
        self._timer.start(16)

        self._cycle = QtCore.QTimer(self.widget)
        self._cycle.timeout.connect(self.next_expression)
        if not os.environ.get("MOCHI_NO_CYCLE"):
            self._cycle.start(self.dwell_ms)

    # ── the window ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        QtCore, QtGui, QtWidgets = self._QtCore, self._QtGui, self._QtWidgets

        self.widget = QtWidgets.QWidget()

        self.screen = QtWidgets.QLabel()
        self.screen.setAlignment(QtCore.Qt.AlignCenter)
        self.screen.setMinimumSize(256, 256)
        self.screen.setStyleSheet("background:#000; border:1px solid #22222c;")

        # ── which pack ──
        # The list comes off the filesystem, so exporting a folder from
        # Anima Studio into assets/characters/ is the whole install.
        self.pack_box = QtWidgets.QComboBox()
        self.pack_box.addItems(animation.available())
        self.pack_box.setCurrentText(self.character.name)
        self.pack_box.currentTextChanged.connect(self._on_pack_picked)

        # ── expressions: the character's OWN vocabulary ──
        self.expr_box = QtWidgets.QComboBox()
        self.expr_box.addItems(self._expressions)
        self.expr_box.setCurrentText(self.character.default_expression)
        self.expr_box.currentTextChanged.connect(self._on_expression_picked)

        self.mouth_btn = QtWidgets.QPushButton("mouth")
        self.mouth_btn.setCheckable(True)
        self.mouth_btn.toggled.connect(self._on_mouth_toggled)

        self.cycle_btn = QtWidgets.QPushButton("cycle")
        self.cycle_btn.setCheckable(True)
        self.cycle_btn.setChecked(not os.environ.get("MOCHI_NO_CYCLE"))
        self.cycle_btn.toggled.connect(self._on_cycle_toggled)

        open_btn = QtWidgets.QPushButton("Open file…")
        open_btn.clicked.connect(self.open_asset)

        back_btn = QtWidgets.QPushButton("← character")
        back_btn.clicked.connect(self.back_to_character)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color:#6a6a78;")

        row = QtWidgets.QHBoxLayout()
        for w in (QtWidgets.QLabel("pack:"), self.pack_box,
                  QtWidgets.QLabel("face:"), self.expr_box, self.mouth_btn,
                  self.cycle_btn):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(open_btn)
        row.addWidget(back_btn)

        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.screen, 1)
        layout.addLayout(row)
        layout.addWidget(self.status)


    # ── driving the engine ───────────────────────────────────────

    def show_expression(self, expression: str, mouth: str | None = None) -> None:
        """Ask the engine for a face. Mechanism, not policy: which cell
        of which atlas, never what mood to be in."""
        self._playing_asset = None
        animation.play(self.bus, self.character, expression,
                       mouth or self._mouth)

    def play_asset(self, path: pathlib.Path) -> None:
        """Play any file the engine has an adapter for.

        ``adapter="auto"`` routes by extension inside the engine, so
        the player needs to know nothing about decoders — a gif, an
        mp4 and a procedural scene are all just a path from here.
        """
        self._playing_asset = path
        self.cycle_btn.setChecked(False)
        animation.play_file(self.bus, path)
        self.status.setText(f"playing {path.name}")

    def next_expression(self) -> None:
        names = self._expressions
        self._expression_idx = (self._expression_idx + 1) % len(names)
        name = names[self._expression_idx]
        self.expr_box.blockSignals(True)
        self.expr_box.setCurrentText(name)
        self.expr_box.blockSignals(False)
        self.show_expression(name)

    def back_to_character(self) -> None:
        self.show_expression(self.expr_box.currentText())
        self.status.setText("")

    def open_asset(self) -> None:
        path, _ = self._QtWidgets.QFileDialog.getOpenFileName(
            self.widget, "Play a file", str(pathlib.Path.home()), _FILE_FILTER)
        if path:
            self.play_asset(pathlib.Path(path))

    # ── control callbacks ────────────────────────────────────────

    def _on_pack_picked(self, name: str) -> None:
        """Swap characters live.

        The expression list is rebuilt from the new pack, because the
        vocabulary belongs to the character — two packs need not share
        a single word.
        """
        try:
            self.character = animation.load(name)
        except animation.CharacterError as exc:
            self.status.setText(str(exc))
            return
        self._expressions = list(self.character.expressions)
        self._expression_idx = 0
        self._mouth = self.character.default_mouth
        self.expr_box.blockSignals(True)
        self.expr_box.clear()
        self.expr_box.addItems(self._expressions)
        self.expr_box.setCurrentText(self.character.default_expression)
        self.expr_box.blockSignals(False)
        self.mouth_btn.setChecked(False)
        self.show_expression(self.character.default_expression)

    def _on_expression_picked(self, name: str) -> None:
        self._expression_idx = self._expressions.index(name)
        self.show_expression(name)

    def _on_mouth_toggled(self, checked: bool) -> None:
        states = list(self.character.mouth_states)
        self._mouth = states[1] if (checked and len(states) > 1) else states[0]
        if self._playing_asset is None:
            self.show_expression(self.expr_box.currentText())

    def _on_cycle_toggled(self, checked: bool) -> None:
        if checked and self._playing_asset is None:
            self._cycle.start(self.dwell_ms)
        else:
            self._cycle.stop()

    # ── the bus side ─────────────────────────────────────────────

    def _on_frame(self, msg: Any) -> None:
        """Bus thread. Build the image and hand it over; do NOT touch a
        widget here."""
        QtGui = self._QtGui
        if not msg.data or msg.width <= 0 or msg.height <= 0:
            return
        image = QtGui.QImage(
            bytes(msg.data), msg.width, msg.height,
            msg.width * 4, QtGui.QImage.Format_RGBA8888,
        )
        # QImage does not own the buffer it was handed. Copy before
        # those bytes go out of scope, or the window paints freed
        # memory — which looks like corruption, not a crash.
        self._frame = image.copy()

    def _on_state(self, msg: Any) -> None:
        """The engine reporting back — chiefly why a clip stopped.

        Stashed rather than shown: this runs on the bus thread, and
        setting a widget's text from there is the same crash as
        painting from there.
        """
        if getattr(msg, "reason", ""):
            self._status_text = msg.reason

    # ── the GUI side ─────────────────────────────────────────────

    def _repaint(self) -> None:
        if self._status_text is not None:
            self.status.setText(self._status_text)
            self._status_text = None
        frame = self._frame
        if frame is None:
            return
        QtCore, QtGui = self._QtCore, self._QtGui
        self.screen.setPixmap(QtGui.QPixmap.fromImage(frame).scaled(
            self.screen.width(), self.screen.height(),
            QtCore.Qt.KeepAspectRatio,
            # Pixel art: any smoothing destroys exactly what makes a
            # 128x128 sprite readable. The pack asks for nearest and
            # this is where that request has to be honoured.
            QtCore.Qt.FastTransformation
            if animation.scaling(self.character) == "nearest"
            else QtCore.Qt.SmoothTransformation,
        ))

    # ── lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        asset = os.environ.get("MOCHI_ASSET")
        if asset:
            self.play_asset(pathlib.Path(asset))
        else:
            self.show_expression(self.character.default_expression)

    def close(self) -> None:
        try:
            self._timer.stop()
            self._cycle.stop()
            self.bus.unsubscribe(_FRAME, self._on_frame)
            self.bus.unsubscribe(_STATE, self._on_state)
        except Exception:  # noqa: BLE001
            pass




__all__ = ["FaceTab"]
