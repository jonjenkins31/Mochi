"""Current-bus version of the classic Mochi virtual LED display."""

from __future__ import annotations

import time
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets
from jaeger_os import topics


class VirtualDisplayWindow(QtWidgets.QMainWindow):
    def __init__(self, bus: Any, zoom: int = 2) -> None:
        super().__init__()
        self.bus = bus; self.zoom = max(1, zoom)
        self.setWindowTitle("Mochi Virtual Display")
        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central); layout.setContentsMargins(0, 0, 0, 0)
        self.screen = QtWidgets.QLabel("waiting for /act/display/frame")
        self.screen.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.screen.setStyleSheet("background:#000;color:#777;")
        layout.addWidget(self.screen, 1)
        row = QtWidgets.QHBoxLayout()
        self.info = QtWidgets.QLabel("-- × --")
        self.fps = QtWidgets.QLabel("FPS: --")
        row.addWidget(self.info); row.addStretch(1); row.addWidget(self.fps)
        layout.addLayout(row)
        self.resize(540, 560)
        self._pending: QtGui.QImage | None = None
        self._last_t = time.monotonic(); self._frames = 0
        bus.subscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        self._timer = QtCore.QTimer(self); self._timer.timeout.connect(self._drain)
        self._timer.start(16)

    def _on_frame(self, msg: Any) -> None:
        if not getattr(msg, "data", None):
            return
        image = QtGui.QImage(bytes(msg.data), msg.width, msg.height, msg.width * 4,
                             QtGui.QImage.Format.Format_RGBA8888)
        self._pending = image.copy()

    def _drain(self) -> None:
        image, self._pending = self._pending, None
        if image is None:
            return
        self.screen.setPixmap(QtGui.QPixmap.fromImage(image).scaled(
            self.screen.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation))
        self.info.setText(f"{image.width()} × {image.height()}  zoom {self.zoom}×")
        self._frames += 1
        now = time.monotonic()
        if now - self._last_t >= 1.0:
            self.fps.setText(f"FPS: {self._frames / (now - self._last_t):.1f}")
            self._last_t, self._frames = now, 0

    def show_window(self) -> None:
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        event.ignore(); self.hide()

    def shutdown(self) -> None:
        self._timer.stop()
        try:
            self.bus.unsubscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        except Exception:  # noqa: BLE001
            pass
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        super().close()


__all__ = ["VirtualDisplayWindow"]

