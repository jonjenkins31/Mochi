"""The character, and nothing else — Mochi's one avatar surface.

    /act/display/frame ──▶ CharacterView

That is the entire contract, and it is why this file is short. The view
never calls the animation engine, never learns which adapter is running,
and imports nothing from it beyond the per-pack scaling rule. Frames
arrive as RGBA8888 on a topic and get blitted.

WHY IT EXISTS AT ALL. Mochi grew four windows that all show the same
frames — the Face tab's panel, the skinnable popup with its bezel, the
v4 media popup, the LED-matrix simulator — plus JaegerAI's AvatarView,
which is the same widget again. This is the one that stays. The design
is JaegerAI's (a plain scaled surface, embeddable or standing alone);
the pixel-art rule is Mochi's, and it is the one thing the JaegerAI
version gets wrong: it always smooths, which is exactly what makes a
128×128 sprite unreadable.

Embeddable AND a window, because in Qt a parentless QWidget already is
one. Two classes for that would be one class too many.
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets
from jaeger_os import topics

from modules import jaeger_animation as animation


class CharacterView(QtWidgets.QWidget):
    """A live view of whatever is on the display bus."""

    def __init__(self, app: Any, *, character_of: Any = None,
                 title: str = "Mochi — character") -> None:
        """`character_of` is a CALLABLE, not a character: the pack can be
        swapped from the Face tab while this window is open, and asking
        at paint time is a lambda where keeping it in sync is a signal,
        a slot and a way to be wrong."""
        super().__init__()
        self.bus = app.bus
        self.character_of = character_of
        self.setWindowTitle(title)
        self.setObjectName("CharacterView")
        self.setStyleSheet(
            "QWidget#CharacterView{background:#0B0910;}"
            "QLabel#Screen{color:#8A85A6;font-size:13px;}")
        self.resize(420, 420)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.screen = QtWidgets.QLabel("waiting for a frame…")
        self.screen.setObjectName("Screen")
        self.screen.setAlignment(QtCore.Qt.AlignCenter)
        self.screen.setMinimumSize(160, 160)
        layout.addWidget(self.screen)

        # Written by the bus thread, read by the timer. One reference
        # swap, so no lock: the reader either sees the old frame or the
        # new one and both are whole.
        self._frame: QtGui.QImage | None = None
        self.bus.subscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._repaint)
        self._timer.start(33)

    def _on_frame(self, msg: Any) -> None:
        """Bus thread. Build the image; touch no widget."""
        if not msg.data or msg.width <= 0 or msg.height <= 0:
            return
        image = QtGui.QImage(bytes(msg.data), msg.width, msg.height,
                             msg.width * 4, QtGui.QImage.Format_RGBA8888)
        # QImage does not own the buffer it was handed — copy before
        # those bytes go out of scope, or this paints freed memory.
        self._frame = image.copy()

    def _repaint(self) -> None:
        frame = self._frame
        if frame is None or not self.isVisible():
            return
        smooth = False
        if self.character_of is not None:
            try:
                smooth = animation.scaling(self.character_of()) != "nearest"
            except Exception:  # noqa: BLE001 — a scaling hint, not a feature
                pass
        self.screen.setPixmap(QtGui.QPixmap.fromImage(frame).scaled(
            self.screen.size(), QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation if smooth
            else QtCore.Qt.FastTransformation))

    def show_window(self) -> None:
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        """Hide rather than die. The window manager holds one of these
        and reopening it must not rebuild a bus subscription."""
        event.ignore()
        self.hide()

    def shutdown(self) -> None:
        self._timer.stop()
        try:
            self.bus.unsubscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        except Exception:  # noqa: BLE001
            pass
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        super().close()


__all__ = ["CharacterView"]
