"""Vision tab — what the camera sees.

    /sense/camera/image_raw  ──▶  the preview, and the frame counter

The same shape as Hearing, and for the same reason: "the camera isn't
working" has several very different causes — no node running, a device
index that is not the camera you meant, a permission the OS never
granted — and a black rectangle cannot tell them apart. A preview with
a moving frame count says the capture path is fine and something
downstream is not; a still one says stop looking downstream.

THIS TAB OWNS THE EYES. `set_node()` is the whole switch, because the
camera is not shared with anything: the audio driver needed
`core/audio_switch.py` to reconcile two engines fighting over one
device, and vision has one engine and one device.

Nothing here decodes a frame or imports OpenCV. It subscribes, hands
the encoded bytes to Qt, and draws what comes back — the node is the
eyes and this is a window onto them. Turning frames into MEANING is a
separate node on /sense/vision/analysis that does not exist yet; when
it does, nothing in this file has to change.
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

from jaeger_os import topics

from core.module_support import (
    VISION_NODE, background, node_state, set_node, settings)

#: The one topic a camera publishes. Named here rather than imported
#: from a `modules/` integration because there is no module — vision is
#: a framework node, like the audio driver.
CAMERA = topics.SENSE_CAMERA_IMAGE_RAW


class VisionTab:
    """Switch the camera on and watch what it sees."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui = QtCore, QtGui
        self.app = app
        self.bus = app.bus

        self._pending: list[str] = []
        self._switches: list[str] = []
        self._frame: Any = None          # written by the bus thread
        # The drain CONSUMES `_frame` when it paints, so Capture needs
        # its own hold on the latest one — otherwise the button works or
        # not depending on where the 50ms repaint happened to land.
        self._last_saved_frame: Any = None
        self.captured: Any = None        # the last still written, if any
        self.project_root = pathlib.Path(__file__).resolve().parent.parent
        self._frames = 0
        self._last_frame_at = 0.0
        self._declared = node_state(app, VISION_NODE) != ""

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)

        # ── on, and which camera ──
        bar = QtWidgets.QHBoxLayout()
        self.power = QtWidgets.QCheckBox("Eyes")
        self.power.setToolTip(
            "start and stop the camera node. The webcam is opened only "
            "while this is on." if self._declared
            else "no vision node in this manifest")
        self.power.setEnabled(self._declared)
        self.power.toggled.connect(self._power_toggled)
        bar.addWidget(self.power)
        bar.addSpacing(10)

        bar.addWidget(QtWidgets.QLabel("device"))
        self.device = QtWidgets.QSpinBox()
        self.device.setRange(0, 15)
        self.device.setValue(int(settings(app, VISION_NODE).get("device_index", 0)))
        self.device.setToolTip(
            "which camera. 0 is the built-in one; a plugged-in webcam is "
            "usually 1. Read when the node STARTS, so changing it while "
            "the eyes are open restarts them.")
        self.device.valueChanged.connect(self._device_chosen)
        bar.addWidget(self.device)
        self.capture_button = QtWidgets.QPushButton("Capture")
        self.capture_button.setToolTip(
            "save the frame on screen as a still. This is the input every "
            "path forward wants — a VLM, an analysis node, or a multimodal "
            "chat — none of which can take a live stream.")
        self.capture_button.clicked.connect(self.capture)
        bar.addWidget(self.capture_button)
        bar.addStretch(1)
        self.status = QtWidgets.QLabel()
        self.status.setStyleSheet("color:#6a6a78;")
        bar.addWidget(self.status)
        layout.addLayout(bar)

        self.preview = QtWidgets.QLabel()
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumSize(320, 240)
        self.preview.setStyleSheet("background:#000; border:1px solid #33333f;")
        self.preview.setText("eyes off")
        layout.addWidget(self.preview, 1)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        self.log.setMaximumHeight(120)
        self.log.setPlaceholderText(
            "nothing seen yet.\n\n"
            "A moving frame count with a black preview means the camera is "
            "fine and the decode is not. No frames at all means the device "
            "index is wrong, or macOS never granted camera permission — "
            "that prompt only appears the first time something opens it.")
        layout.addWidget(self.log)

        self.bus.subscribe(CAMERA, self._on_frame)
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(50)            # a preview wants to look live

    # ── driving it ───────────────────────────────────────────────

    def _power_toggled(self, on: bool) -> None:
        """Blocks — opening a camera is slow and can prompt for
        permission — so it goes to a thread like every other switch."""
        if on == (node_state(self.app, VISION_NODE) == "running"):
            return                       # the tick came from _drain re-syncing
        self.power.setEnabled(False)
        self._pending.append(f"eyes {'starting' if on else 'stopping'}…")
        background(lambda: set_node(self.app, VISION_NODE, on), self._switches)

    def capture(self) -> str:
        """Write the frame on screen to a file. Returns the path, or "".

        A STILL, deliberately. Nothing downstream of a camera consumes a
        stream: a VLM takes an image path, an analysis node takes one
        frame at a time, and a multimodal chat turn carries one picture.
        The encoded bytes are saved exactly as the camera produced them
        rather than re-encoded from the preview, so what gets looked at
        is what the sensor saw and not what fitted in a label.
        """
        frame = self._last_saved_frame
        if frame is None:
            self._pending.append("nothing captured — no frame yet")
            return ""
        directory = self.project_root / "assets" / "captures"
        directory.mkdir(parents=True, exist_ok=True)
        suffix = {"jpeg": ".jpg", "png": ".png"}.get(
            str(getattr(frame, "encoding", "")), ".bin")
        path = directory / f"{time.strftime('%Y%m%d-%H%M%S')}{suffix}"
        try:
            path.write_bytes(bytes(getattr(frame, "frame_bytes", b"")))
        except OSError as exc:
            self._pending.append(f"capture failed — {exc}")
            return ""
        self._pending.append(
            f"captured {path.relative_to(self.project_root)} "
            f"({getattr(frame, 'image_w', 0)}×{getattr(frame, 'image_h', 0)})")
        self.captured = path
        return str(path)

    def _device_chosen(self, index: int) -> None:
        """Pick a camera. Read when the node is BUILT, so a live change
        is a restart — the same shape as swapping the STT engine."""
        # The live slice, not `settings()`'s copy: this is the dict the
        # node's factory re-reads on every start.
        (self.app.config or {}).setdefault(VISION_NODE, {})["device_index"] = index
        self._pending.append(f"device → {index}")
        if node_state(self.app, VISION_NODE) != "running":
            return                       # takes effect the next time it starts
        self.power.setEnabled(False)
        background(
            lambda: (set_node(self.app, VISION_NODE, False)
                     or set_node(self.app, VISION_NODE, True)),
            self._switches)

    # ── bus thread: record only ──────────────────────────────────

    def _on_frame(self, msg: Any) -> None:
        """Keep the LATEST frame and nothing else.

        Runs on the bus delivery thread, so it decodes nothing and
        touches no widget. Queuing frames would mean a slow paint loop
        rendering a backlog of stale pictures — the adapter already
        drops rather than lags, and this keeps that property.
        """
        self._frames += 1
        self._last_frame_at = time.monotonic()
        self._frame = msg
        self._last_saved_frame = msg

    # ── GUI thread ───────────────────────────────────────────────

    def _drain(self) -> None:
        stamp = time.strftime("%H:%M:%S")
        while self._pending:
            self.log.appendPlainText(f"{stamp}  {self._pending.pop(0)}")
        while self._switches:
            failed = self._switches.pop(0)
            if failed:
                self.log.appendPlainText(f"{stamp}  not done — {failed}")
            self.power.setEnabled(self._declared)

        running = node_state(self.app, VISION_NODE) == "running"
        if self.power.isChecked() != running:
            self.power.blockSignals(True)
            self.power.setChecked(running)
            self.power.blockSignals(False)

        self._repaint(running)

    def _repaint(self, running: bool) -> None:
        if not self._declared:
            self.status.setText("no vision node in this manifest")
            return
        if not running:
            self.status.setText("eyes: off")
            self.preview.setText("eyes off")
            self.preview.setPixmap(self._QtGui.QPixmap())
            return

        stale = self._last_frame_at and time.monotonic() - self._last_frame_at > 1.5
        if not self._frames:
            self.status.setText("eyes: on, waiting for /sense/camera/image_raw")
        elif stale:
            self.status.setText(
                f"eyes: STOPPED — {self._frames} frames, then nothing")
        else:
            self.status.setText(f"eyes: live, {self._frames} frames")

        msg, self._frame = self._frame, None
        if msg is None:
            return
        image = self._QtGui.QImage()
        # Qt decodes jpeg/png itself. `raw_*` has no container for it to
        # read, so it is reported rather than drawn as a black rectangle
        # that looks like a dead camera.
        if not image.loadFromData(bytes(getattr(msg, "frame_bytes", b""))):
            self.preview.setText(
                f"{getattr(msg, 'encoding', '?')} frames — no preview\n"
                f"{getattr(msg, 'image_w', 0)}×{getattr(msg, 'image_h', 0)}, "
                f"set encoding = \"jpeg\" in [config.vision] to see them")
            return
        self.preview.setPixmap(self._QtGui.QPixmap.fromImage(image).scaled(
            self.preview.size(), self._QtCore.Qt.KeepAspectRatio,
            self._QtCore.Qt.SmoothTransformation))

    def close(self) -> None:
        self._timer.stop()
        try:
            self.bus.unsubscribe(CAMERA, self._on_frame)
        except Exception:  # noqa: BLE001
            pass


__all__ = ["VisionTab", "CAMERA"]
