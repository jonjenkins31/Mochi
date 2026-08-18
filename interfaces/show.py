"""The Show tab — the operator surface for building one Short.

Three panels, in the order the work happens:

    ┌ output ────────────────┬ cue ──────────┐
    │  the final frame,      │ what is under │
    │  in its delivery       │ the playhead  │
    │  aspect                │               │
    ├────────────────────────┴───────────────┤
    │ ⏮ ▶ ⏸ ⏹  loop  0:04.320 / 0:22.000     │
    ├────────────────────────────────────────┤
    │ the timeline                           │
    └────────────────────────────────────────┘

WHY THE OUTPUT PANEL IS FRAMED. Every other view in this app shows the
character at whatever size the widget happens to be. This one shows the
DELIVERABLE — 9:16 by default, because that is what a Short is — with
the rest of the panel letterboxed off. An operator composing a shot has
to see the frame they are actually shipping, not a preview that crops
differently to the export.

WHY IT IS NOT THE STAGE TAB. Stage drives a character by hand: press a
button, it does a thing. This drives a SHOW on a clock, which is the
opposite job — nothing here fires except because the playhead reached
it.
"""

from __future__ import annotations

import pathlib
from typing import Any

from core import director, staging
from . import theme

#: Delivery aspects an operator actually ships. Vertical first: it is
#: what this is for.
ASPECTS = {"9:16 vertical": (9, 16), "1:1 square": (1, 1),
           "16:9 landscape": (16, 9), "4:5 portrait": (4, 5)}


class OutputView:
    """The final frame, letterboxed to its delivery aspect."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui = QtCore, QtGui
        from jaeger_os import topics

        self.bus = app.bus
        self.aspect = ASPECTS["9:16 vertical"]
        self.widget = QtWidgets.QLabel("no output yet")
        self.widget.setObjectName("Screen")
        self.widget.setAlignment(QtCore.Qt.AlignCenter)
        self.widget.setMinimumSize(180, 300)
        self._frame = None
        self.bus.subscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        self._topic = topics.ACT_DISPLAY_FRAME

    def _on_frame(self, msg: Any) -> None:
        """Bus thread. Build the image, touch no widget."""
        QtGui = self._QtGui
        if not msg.data or msg.width <= 0 or msg.height <= 0:
            return
        image = QtGui.QImage(bytes(msg.data), msg.width, msg.height,
                             msg.width * 4, QtGui.QImage.Format_RGBA8888)
        self._frame = image.copy()

    def repaint(self) -> None:
        frame = self._frame
        if frame is None:
            return
        QtCore, QtGui = self._QtCore, self._QtGui
        # The delivery frame INSIDE the panel: whatever is left over is
        # letterbox, and is drawn as such rather than filled with the
        # character, so composition is judged against the real edges.
        box = self.widget.size()
        ratio = self.aspect[0] / self.aspect[1]
        width = min(box.width(), int(box.height() * ratio))
        height = int(width / ratio)
        if width < 8 or height < 8:
            return
        canvas = QtGui.QPixmap(box)
        canvas.fill(QtGui.QColor("#0A0A0E"))
        painter = QtGui.QPainter(canvas)
        target = QtCore.QRect((box.width() - width) // 2,
                              (box.height() - height) // 2, width, height)
        painter.fillRect(target, QtGui.QColor("#000000"))
        scaled = QtGui.QPixmap.fromImage(frame).scaled(
            target.size(), QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation)
        painter.drawPixmap(
            target.x() + (target.width() - scaled.width()) // 2,
            target.y() + (target.height() - scaled.height()) // 2, scaled)
        painter.setPen(QtGui.QColor("#2A2A38"))
        painter.drawRect(target.adjusted(0, 0, -1, -1))
        painter.end()
        self.widget.setPixmap(canvas)

    def close(self) -> None:
        try:
            self.bus.unsubscribe(self._topic, self._on_frame)
        except Exception:  # noqa: BLE001
            pass


class ShowTab:
    """Load a show, scrub it, and watch the frame you are shipping."""

    def __init__(self, app: Any, qt: tuple, character_of: Any = None) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtWidgets = QtCore, QtWidgets
        self.app = app
        self.character_of = character_of
        self._lines: list[str] = []
        self.stage = director.Director(
            app, on_event=self._lines.append,
            on_tick=lambda *_: None)

        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.widget)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._top(app, qt), 3)
        root.addWidget(self._transport())
        from .timeline_panel import TimelinePanel

        self.timeline = TimelinePanel(self.stage, on_pick=self._show_cue)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(self.timeline)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(150)
        root.addWidget(scroll, 2)

        self.status = QtWidgets.QLabel("open a show to begin.")
        self.status.setObjectName("Dim")
        root.addWidget(self.status)

        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(50)

    # ── layout ───────────────────────────────────────────────────

    def _top(self, app: Any, qt: tuple):
        QtWidgets = self._QtWidgets
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        left = QtWidgets.QVBoxLayout()
        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("OUTPUT")
        title.setObjectName("Hint")
        head.addWidget(title)
        head.addStretch(1)
        self.aspect_box = QtWidgets.QComboBox()
        self.aspect_box.addItems(list(ASPECTS))
        self.aspect_box.currentTextChanged.connect(self._aspect_chosen)
        head.addWidget(self.aspect_box)
        left.addLayout(head)
        self.output = OutputView(app, qt)
        left.addWidget(self.output.widget, 1)
        layout.addLayout(left, 3)

        side = QtWidgets.QVBoxLayout()
        picked = QtWidgets.QLabel("CUE")
        picked.setObjectName("Hint")
        side.addWidget(picked)
        self.inspector = QtWidgets.QPlainTextEdit()
        self.inspector.setReadOnly(True)
        self.inspector.setPlaceholderText("click a clip in the timeline.")
        side.addWidget(self.inspector, 1)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        self.log.setPlaceholderText("what the transport is doing.")
        side.addWidget(self.log, 1)
        layout.addLayout(side, 2)
        return row

    def _transport(self):
        QtWidgets = self._QtWidgets
        bar = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)

        self.open_box = QtWidgets.QComboBox()
        self.open_box.setMinimumWidth(220)
        for label, path in staging.available(None):
            self.open_box.addItem(label, str(path))
        self.open_box.currentIndexChanged.connect(self._open_chosen)
        row.addWidget(self.open_box)

        for label, slot, tip in (
                ("⏮", lambda: self.stage.seek(self.stage.start_ms), "to start"),
                ("▶", self.stage.play, "play"),
                ("⏸", self.stage.pause, "pause"),
                ("⏹", self.stage.stop, "stop")):
            button = QtWidgets.QPushButton(label)
            button.setFixedWidth(40)
            button.setToolTip(tip)
            button.clicked.connect(lambda _c=False, s=slot: s())
            row.addWidget(button)

        self.loop_btn = QtWidgets.QPushButton("loop")
        self.loop_btn.setCheckable(True)
        self.loop_btn.toggled.connect(
            lambda on: setattr(self.stage, "loop", bool(on)))
        row.addWidget(self.loop_btn)
        clear = QtWidgets.QPushButton("clear range")
        clear.setToolTip("alt-drag the timeline to set a loop region")
        clear.clicked.connect(lambda: (self.stage.set_region(None),
                                       self.timeline.update()))
        row.addWidget(clear)

        row.addWidget(QtWidgets.QLabel("pre-roll"))
        self.preroll = QtWidgets.QSpinBox()
        self.preroll.setRange(0, 10)
        self.preroll.setSuffix("s")
        self.preroll.valueChanged.connect(
            lambda v: setattr(self.stage, "preroll_ms", int(v) * 1000))
        row.addWidget(self.preroll)

        self.render_btn = QtWidgets.QPushButton("render dialogue")
        self.render_btn.setToolTip(
            "synthesise every written line to a file, once. The timeline "
            "then knows how long speech ACTUALLY is, and scrubbing plays "
            "audio from an offset instead of talking over itself.")
        self.render_btn.clicked.connect(self.render_dialogue)
        row.addWidget(self.render_btn)

        fit = QtWidgets.QPushButton("fit")
        fit.clicked.connect(lambda: self.timeline.fit())
        row.addWidget(fit)
        row.addStretch(1)
        self.clock = QtWidgets.QLabel("0:00.000 / 0:00.000")
        self.clock.setStyleSheet("font-family:ui-monospace,Menlo,monospace;")
        row.addWidget(self.clock)
        return bar

    # ── driving it ───────────────────────────────────────────────

    def open_show(self, path: Any) -> None:
        try:
            timeline = staging.load(path)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"could not open: {exc}")
            return
        self.stage.load(timeline)
        self.timeline.fit(self.timeline.parent().width()
                          if self.timeline.parent() else None)
        self.timeline.update()
        dead = self.stage.unsupported()
        self.status.setText(
            f"{timeline.name} — {len(timeline.tracks)} tracks, "
            f"{len(self.stage.cues)} cues, "
            f"{director.duration_of(timeline) / 1000:.1f}s"
            + (f"   ⚠ {len(dead)} track(s) play nowhere" if dead else ""))

    def render_dialogue(self) -> None:
        """Render every written line, then retime the show to match.

        Blocks: synthesis is seconds of work and an operator pressed
        the button. A progress line per line beats a spinner that says
        nothing about which one is slow.
        """
        from core import dialogue

        if self.stage.timeline is None:
            return
        self.render_btn.setEnabled(False)
        self.status.setText("rendering dialogue…")
        self._QtWidgets.QApplication.processEvents()
        report = dialogue.render(
            self.stage.timeline, root=pathlib.Path(
                getattr(self.app, "root", pathlib.Path.cwd())),
            on_line=lambda text, hit: self._lines.append(
                f"{'cached ' if hit else 'rendered'}  {text}"))
        # Durations changed, so the show is a different length and the
        # cues have to be rebuilt against it.
        self.stage.load(self.stage.timeline)
        self.timeline.fit()
        self.timeline.update()
        self.render_btn.setEnabled(True)
        failed = len(report["failed"])
        self.status.setText(
            f"rendered {report['rendered']}, cached {report['cached']}"
            + (f", {failed} failed" if failed else "")
            + f" — timing corrected by {report['moved_ms'] / 1000:.1f}s")
        for line in report["failed"][:5]:
            self._lines.append(f"! {line}")

    def _open_chosen(self, index: int) -> None:
        path = self.open_box.itemData(index)
        if path:
            self.open_show(pathlib.Path(path))

    def _aspect_chosen(self, name: str) -> None:
        self.output.aspect = ASPECTS.get(name, (9, 16))
        self.output.repaint()

    def _show_cue(self, cue: Any) -> None:
        clip = cue.clip
        payload = dict(clip.payload or {})
        lines = [f"track   {cue.track}   ({cue.kind})",
                 f"target  {cue.target or '—'}",
                 f"at      {cue.at_ms} ms",
                 f"for     {clip.duration_ms} ms", ""]
        lines += [f"{key:<8}{value}" for key, value in payload.items()]
        self.inspector.setPlainText("\n".join(lines))

    def _drain(self) -> None:
        while self._lines:
            self.log.appendPlainText(self._lines.pop(0))
        self.output.repaint()
        if self.stage.timeline is None:
            return
        self.clock.setText(
            f"{_clock(self.stage.position_ms)} / "
            f"{_clock(self.stage.duration_ms)}   {self.stage.state}")
        if self.stage.state in (director.PLAYING, director.PREROLL):
            self.timeline.update()

    def close(self) -> None:
        self._timer.stop()
        self.stage.stop()
        self.output.close()


def _clock(ms: int) -> str:
    ms = max(0, int(ms))
    return f"{ms // 60000:d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


__all__ = ["ShowTab", "OutputView", "ASPECTS"]
