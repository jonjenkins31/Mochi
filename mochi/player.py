"""The window — a subscriber that happens to have pixels in it.

    /act/display/frame ──▶ PlayerWindow

That is the whole contract. The window does not call the animation
engine, does not know which adapter is running, and does not import
anything from it. It receives RGBA frames on a topic and blits them.

Which is why the same engine drives an LED matrix and JP01's face:
they are different subscribers, not different code paths. If this file
ever imports `jaeger_animation`, that property is gone.

The reverse direction is just as thin. To change the face, Mochi
publishes a DisplayCommand — asset plus adapter plus params — and the
engine decides what that means. Mochi never sends "be happy"; it sends
"play cell 6 of this atlas", having looked up what "happy" means in the
CHARACTER's own vocabulary.
"""

from __future__ import annotations

import sys
from typing import Any

from jaeger_os.transport import topics

from . import character as character_mod

#: Idle behaviour for v5.0. With no mind attached, the player walks the
#: character's expressions so you can see the whole vocabulary — which
#: is also the fastest way to tell a pack is wired correctly.
_IDLE_CYCLE = True


def _qt():
    """Import PySide6 with an error that says what to install."""
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:  # pragma: no cover - env dependent
        raise RuntimeError(
            "Mochi's window needs PySide6 — the ecosystem's standard "
            "cross-platform GUI toolkit. Install it with:\n"
            "    pip install pyside6"
        ) from exc
    return QtCore, QtGui, QtWidgets


class PlayerWindow:
    """A frameless always-on-top window showing whatever is on
    ``/act/display/frame``."""

    def __init__(self, app: Any, config: dict[str, Any]) -> None:
        QtCore, QtGui, QtWidgets = _qt()
        self._QtCore, self._QtGui = QtCore, QtGui

        self.bus = app.bus
        self.config = config
        self.character = character_mod.load(config.get("character", "emotes"))
        self.scale = int(config.get("scale", 2))
        self.dwell_ms = int(float(config.get("dwell_s", 1.5)) * 1000)

        self._frame = None          # QImage, written by the bus thread
        self._expression_idx = 0

        self.widget = QtWidgets.QLabel()
        self.widget.setWindowTitle(f"Mochi — {self.character.name}")
        self.widget.setAlignment(QtCore.Qt.AlignCenter)
        self.widget.setStyleSheet("background: #101014;")
        self.widget.resize(256 * self.scale, 256 * self.scale)

        # Repaint on the GUI thread, never from the bus callback. Qt
        # widgets are not thread-safe, and a subscriber callback runs on
        # the bus's delivery thread — touching the widget there is a
        # crash that only shows up under load.
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._repaint)
        self._timer.start(16)       # ~60 Hz; frames arrive slower

        if _IDLE_CYCLE:
            self._cycle = QtCore.QTimer(self.widget)
            self._cycle.timeout.connect(self.next_expression)
            self._cycle.start(self.dwell_ms)

        self.bus.subscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)

    # ── the bus side ─────────────────────────────────────────────

    def _on_frame(self, msg: Any) -> None:
        """Bus thread. Build the image and hand it over; do NOT touch
        the widget here."""
        QtGui = self._QtGui
        if not msg.data or msg.width <= 0 or msg.height <= 0:
            return
        image = QtGui.QImage(
            bytes(msg.data), msg.width, msg.height,
            msg.width * 4, QtGui.QImage.Format_RGBA8888,
        )
        # QImage does not own the buffer it was handed; copy() before
        # the bytes go out of scope, or the window paints freed memory.
        self._frame = image.copy()

    def show_expression(self, expression: str, mouth: str | None = None) -> None:
        """Ask the engine for a face. Mechanism, not policy: this says
        which cell of which atlas, never what mood to be in."""
        self.bus.publish(topics.DisplayCommand(
            adapter=self.character.adapter,
            asset_path=str(self.character.asset),
            params=self.character.play_params(expression, mouth),
        ))

    def next_expression(self) -> None:
        names = self.character.expression_names
        self._expression_idx = (self._expression_idx + 1) % len(names)
        self.show_expression(names[self._expression_idx])

    # ── the GUI side ─────────────────────────────────────────────

    def _repaint(self) -> None:
        frame = self._frame
        if frame is None:
            return
        QtCore, QtGui = self._QtCore, self._QtGui
        pixmap = QtGui.QPixmap.fromImage(frame).scaled(
            self.widget.width(), self.widget.height(),
            QtCore.Qt.KeepAspectRatio,
            # Pixel art: any smoothing destroys exactly what makes a
            # 128x128 sprite readable. The pack asks for nearest and
            # this is where that request has to be honoured.
            QtCore.Qt.FastTransformation
            if self.character.scaling == "nearest"
            else QtCore.Qt.SmoothTransformation,
        )
        self.widget.setPixmap(pixmap)

    def start(self) -> None:
        self.widget.show()
        self.show_expression(self.character.default_expression)

    def close(self) -> None:
        try:
            self._timer.stop()
            if _IDLE_CYCLE:
                self._cycle.stop()
            self.bus.unsubscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        except Exception:  # noqa: BLE001
            pass
        self.widget.close()


def make_player(app: Any, spec: Any) -> PlayerWindow:
    """Surface factory named by ``jaeger.toml``."""
    config = {}
    try:
        config = (app.config or {}).get("player", {}) or {}
    except Exception:  # noqa: BLE001
        pass
    window = PlayerWindow(app, config)
    window.start()
    return window


__all__ = ["PlayerWindow", "make_player"]
