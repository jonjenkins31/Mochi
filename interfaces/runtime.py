"""Manual controls: every node's switch, raw display commands, telemetry.

THE OLD PANEL, REBUILT. Mochi 3.0's Tk control panel had a node status
strip and Turn On / Turn Off / Reset beside the display commands, and
that half never made it into v5 — the switches came back one at a time,
scoped to a tab (mic and speakers under Hearing and Voice, the camera
under Vision), which is right for an operator asking "can it hear me"
and useless for one asking "what is actually running".

So the strip is back and it is general: whatever the manifest declares
gets a row, including nodes no tab knows about. The per-tab switches are
not replaced — they carry meaning a generic row cannot (the ears and the
voice share one audio driver and have to be reconciled) — this is the
floor underneath them.

It is also the honest performance readout for the runtime half. The
popup monitor watches frames; nothing until now showed uptime and
restart counts, which is where a node that is quietly dying shows up.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from jaeger_os import topics

from core.module_support import background, set_node
from modules import jaeger_animation as animation
from .player import _FILE_FILTER


class RuntimeTab:
    """Switch nodes, send raw display commands, watch the renderer."""

    def __init__(self, app: Any, qt: tuple, on_monitor: Any = None) -> None:
        QtCore, _QtGui, QtWidgets = qt
        self._QtCore, self._QtWidgets = QtCore, QtWidgets
        self.app = app
        self.bus = app.bus
        self._pending_stats = None
        self._pending_state = None
        self._switches: list[str] = []
        self._rows: dict[str, dict] = {}
        self._busy: set[str] = set()

        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.widget)
        root.setContentsMargins(8, 8, 8, 8)

        root.addWidget(self._node_panel())

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
        # The monitor is a separate WINDOW and that is the point: it can
        # stay open over the Stage tab, which no group box on this page
        # can do. Its button belongs here, where an operator looking for
        # performance actually looks.
        if on_monitor is not None:
            monitor = QtWidgets.QPushButton("Performance monitor…")
            monitor.clicked.connect(lambda: on_monitor())
            buttons.addWidget(monitor)
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

    # ── the node strip ───────────────────────────────────────────

    def _node_panel(self):
        """One row per declared node. Rows are built once — the manifest
        does not change while the app runs, and only the states do."""
        QtWidgets = self._QtWidgets
        box = QtWidgets.QGroupBox("Nodes")
        grid = QtWidgets.QGridLayout(box)
        grid.setColumnStretch(1, 1)

        for column, title in enumerate(("Node", "Backend", "State", "Uptime", "Restarts")):
            head = QtWidgets.QLabel(title)
            head.setStyleSheet("color:#777784;")
            grid.addWidget(head, 0, column)

        for row, entry in enumerate(self._ls(), start=1):
            node_id = entry["id"]
            grid.addWidget(QtWidgets.QLabel(node_id), row, 0)
            grid.addWidget(QtWidgets.QLabel(str(entry.get("backend") or "—")), row, 1)
            cells = {}
            for column, key in ((2, "state"), (3, "uptime"), (4, "restarts")):
                cells[key] = QtWidgets.QLabel("—")
                cells[key].setStyleSheet("font-family:Menlo,monospace;")
                grid.addWidget(cells[key], row, column)
            toggle = QtWidgets.QPushButton("…")
            toggle.setFixedWidth(84)
            toggle.clicked.connect(lambda _=False, n=node_id: self._toggle(n))
            grid.addWidget(toggle, row, 5)
            restart = QtWidgets.QPushButton("Restart")
            restart.clicked.connect(lambda _=False, n=node_id: self._restart(n))
            grid.addWidget(restart, row, 6)
            cells["toggle"], cells["restart"] = toggle, restart
            self._rows[node_id] = cells

        self.node_status = QtWidgets.QLabel(
            "Starting a node opens its device or loads its model, so a switch "
            "can take seconds. A node stopped here stays stopped."
            if self._rows else "No supervisor: nothing to switch.")
        self.node_status.setStyleSheet("color:#777784;")
        grid.addWidget(self.node_status, len(self._rows) + 1, 0, 1, 7)
        return box

    def _ls(self) -> list[dict]:
        supervisor = getattr(self.app, "supervisor", None)
        try:
            return list(supervisor.ls())
        except Exception:  # noqa: BLE001
            return []

    def _toggle(self, node_id: str) -> None:
        cells = self._rows[node_id]
        on = cells["state"].text() != "running"
        self._busy.add(node_id)
        cells["toggle"].setEnabled(False)
        cells["state"].setText("starting…" if on else "stopping…")
        # Every report is prefixed with the node it is about, because two
        # switches can be in flight at once and the drain has to know
        # which row stopped being busy.
        background(lambda: f"{node_id}: " + (
            set_node(self.app, node_id, on) or ("started" if on else "stopped")),
            self._switches)

    def _restart(self, node_id: str) -> None:
        """Stop then start, off the GUI thread. The supervisor's own
        `restart()` would do it in one call and block the window for as
        long as the node takes to come back."""
        self._busy.add(node_id)
        self._rows[node_id]["toggle"].setEnabled(False)
        self._rows[node_id]["state"].setText("restarting…")
        background(lambda: f"{node_id}: " + (set_node(self.app, node_id, False)
                                            or set_node(self.app, node_id, True)
                                            or "restarted"), self._switches)

    def _refresh_nodes(self) -> None:
        while self._switches:
            report = self._switches.pop(0)
            self.node_status.setText(report)
            self._busy.discard(report.partition(":")[0])
        for entry in self._ls():
            cells = self._rows.get(entry["id"])
            if cells is None or entry["id"] in self._busy:
                continue
            state = str(entry.get("state") or "—")
            cells["state"].setText(state)
            uptime = entry.get("uptime_s") or 0
            cells["uptime"].setText(f"{uptime:.0f}s" if state == "running" else "—")
            cells["restarts"].setText(str(entry.get("restarts", 0)))
            cells["toggle"].setEnabled(True)
            cells["toggle"].setText("Turn off" if state == "running" else "Turn on")

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
        self._refresh_nodes()
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
