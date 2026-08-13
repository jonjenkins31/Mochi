"""Performance/health popup retained from the old Mochi monitor."""

from __future__ import annotations

import time
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets
from jaeger_os import topics


class PerformanceWindow(QtWidgets.QWidget):
    def __init__(self, app: Any) -> None:
        super().__init__()
        self.app = app; self.bus = app.bus
        self.setWindowTitle("Mochi Performance Monitor")
        layout = QtWidgets.QGridLayout(self)
        names = ("Render size", "Observed FPS", "Frame sequence", "Animation state", "Nodes")
        self.values: dict[str, QtWidgets.QLabel] = {}
        for row, name in enumerate(names):
            layout.addWidget(QtWidgets.QLabel(f"{name}:"), row, 0)
            value = QtWidgets.QLabel("--"); value.setStyleSheet("font-family:Menlo,monospace;")
            layout.addWidget(value, row, 1); self.values[name] = value
        self.resize(390, 210)
        self._pending_size: tuple[int, int] | None = None
        self._pending_state = ""
        self._frames = 0; self._sequence = 0; self._last_t = time.monotonic()
        self.bus.subscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        self.bus.subscribe(topics.ACT_DISPLAY_STATE, self._on_state)
        self._timer = QtCore.QTimer(self); self._timer.timeout.connect(self._refresh)
        self._timer.start(250)

    def _on_frame(self, msg: Any) -> None:
        self._pending_size = (int(msg.width), int(msg.height))
        self._sequence += 1; self._frames += 1

    def _on_state(self, msg: Any) -> None:
        self._pending_state = str(getattr(msg, "state", "--"))

    def _refresh(self) -> None:
        if self._pending_size:
            self.values["Render size"].setText(
                f"{self._pending_size[0]} × {self._pending_size[1]}")
        self.values["Frame sequence"].setText(str(self._sequence))
        self.values["Animation state"].setText(self._pending_state or "--")
        now = time.monotonic()
        elapsed = now - self._last_t
        if elapsed >= 1.0:
            self.values["Observed FPS"].setText(f"{self._frames / elapsed:.1f}")
            self._last_t, self._frames = now, 0
        supervisor = getattr(self.app, "supervisor", None)
        try:
            rows = supervisor.ls() if supervisor else []
            self.values["Nodes"].setText(
                ", ".join(f"{row['id']}:{row['state']}" for row in rows) or "--")
        except Exception:  # noqa: BLE001
            self.values["Nodes"].setText("unavailable")

    def show_window(self) -> None:
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        event.ignore(); self.hide()

    def shutdown(self) -> None:
        self._timer.stop()
        for topic, handler in ((topics.ACT_DISPLAY_FRAME, self._on_frame),
                               (topics.ACT_DISPLAY_STATE, self._on_state)):
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        super().close()


__all__ = ["PerformanceWindow"]
