"""Manual display controls and live JaegerAnimation telemetry."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from jaeger_os import topics

from modules import jaeger_animation as animation
from .player import _FILE_FILTER


class RuntimeTab:
    """Send raw display commands and explain what the renderer is doing."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, _QtGui, QtWidgets = qt
        self._QtCore, self._QtWidgets = QtCore, QtWidgets
        self.bus = app.bus
        self._pending_stats = None
        self._pending_state = None

        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.widget)
        root.setContentsMargins(8, 8, 8, 8)

        command = QtWidgets.QGroupBox("Manual display command")
        form = QtWidgets.QFormLayout(command)
        self.adapter = QtWidgets.QComboBox()
        self.adapter.addItems(
            ["auto", "image", "bitmap", "sprite", "gif", "video", "math", "mscript"])
        form.addRow("Adapter", self.adapter)

        asset_row = QtWidgets.QHBoxLayout()
        self.asset = QtWidgets.QLineEdit()
        self.asset.setPlaceholderText("asset path")
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        asset_row.addWidget(self.asset, 1)
        asset_row.addWidget(browse)
        form.addRow("Asset", asset_row)

        media_row = QtWidgets.QHBoxLayout()
        self.fit = QtWidgets.QComboBox()
        self.fit.addItems(["contain", "cover", "fill"])
        self.loop = QtWidgets.QCheckBox("Loop")
        self.loop.setChecked(True)
        self.speed = QtWidgets.QDoubleSpinBox()
        self.speed.setRange(0.01, 16.0)
        self.speed.setValue(1.0)
        self.speed.setSuffix("×")
        media_row.addWidget(QtWidgets.QLabel("Fit"))
        media_row.addWidget(self.fit)
        media_row.addWidget(self.loop)
        media_row.addWidget(QtWidgets.QLabel("Speed"))
        media_row.addWidget(self.speed)
        media_row.addStretch(1)
        form.addRow("Media", media_row)

        self.params = QtWidgets.QPlainTextEdit("{}")
        self.params.setMaximumHeight(100)
        self.params.setPlaceholderText('{"src": [0, 0, 128, 128]}')
        form.addRow("Extra params (JSON)", self.params)

        buttons = QtWidgets.QHBoxLayout()
        play = QtWidgets.QPushButton("Play command")
        play.clicked.connect(self.play)
        stop = QtWidgets.QPushButton("Stop / reset")
        stop.clicked.connect(lambda: animation.stop(self.bus))
        buttons.addStretch(1)
        buttons.addWidget(play)
        buttons.addWidget(stop)
        form.addRow(buttons)
        root.addWidget(command)

        stats = QtWidgets.QGroupBox("Animation engine")
        stats_form = QtWidgets.QFormLayout(stats)
        self.fields = {}
        for key, label in (
            ("state", "State"), ("adapter", "Adapter"), ("asset", "Asset"),
            ("geometry", "Render size"), ("fps", "FPS actual / target"),
            ("frames", "Frames emitted / dropped"), ("decode", "Mean decode"),
            ("queue", "Queue depth"), ("reason", "Last reason"),
        ):
            value = QtWidgets.QLabel("—")
            value.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            value.setWordWrap(True)
            self.fields[key] = value
            stats_form.addRow(label, value)
        root.addWidget(stats, 1)

        self.status = QtWidgets.QLabel(
            "Commands use the same /act/display/play path as character preview.")
        self.status.setStyleSheet("color:#777784;")
        root.addWidget(self.status)

        self.bus.subscribe(topics.ACT_DISPLAY_STATS, self._on_stats)
        self.bus.subscribe(topics.ACT_DISPLAY_STATE, self._on_state)
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(200)

    def browse(self) -> None:
        path, _ = self._QtWidgets.QFileDialog.getOpenFileName(
            self.widget, "Choose display asset", str(pathlib.Path.cwd()), _FILE_FILTER)
        if path:
            self.asset.setText(path)

    def play(self) -> None:
        try:
            params = json.loads(self.params.toPlainText() or "{}")
            if not isinstance(params, dict):
                raise ValueError("extra params must be a JSON object")
            params.setdefault("fit", self.fit.currentText())
            params.setdefault("loop", self.loop.isChecked())
            params.setdefault("speed", self.speed.value())
            animation.play_command(
                self.bus, adapter=self.adapter.currentText(),
                asset_path=self.asset.text().strip(), params=params)
            self.status.setText("Display command published")
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Command not sent: {exc}")

    def _on_stats(self, msg: Any) -> None:
        self._pending_stats = msg

    def _on_state(self, msg: Any) -> None:
        self._pending_state = msg

    def _drain(self) -> None:
        msg, self._pending_stats = self._pending_stats, None
        if msg is not None:
            self.fields["adapter"].setText(str(msg.adapter or "—"))
            self.fields["asset"].setText(str(msg.asset_path or "—"))
            self.fields["geometry"].setText(f"{msg.width} × {msg.height}")
            self.fields["fps"].setText(f"{msg.fps_actual:.2f} / {msg.fps_target:.2f}")
            self.fields["frames"].setText(
                f"{msg.frames_emitted} / {msg.frames_dropped}")
            self.fields["decode"].setText(f"{msg.decode_ms:.3f} ms")
            self.fields["queue"].setText(str(msg.queue_depth))
        state, self._pending_state = self._pending_state, None
        if state is not None:
            self.fields["state"].setText(str(state.state))
            self.fields["reason"].setText(str(state.reason or "—"))

    def close(self) -> None:
        self._timer.stop()
        for topic, handler in (
            (topics.ACT_DISPLAY_STATS, self._on_stats),
            (topics.ACT_DISPLAY_STATE, self._on_state),
        ):
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["RuntimeTab"]
