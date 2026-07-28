"""Voice tab — what the TTS module is asked to say, and what happens.

Every widget here is fed by a topic. Nothing imports Kokoro, and the
tab works identically whether a TTS module is installed or not: with
one, the log fills; without, it stays empty and says so. That is the
composition being real rather than claimed.

    /act/speech/say      ──▶  what was asked for
    /act/speech/chunk    ──▶  per-chunk AMPLITUDE — the lip-sync signal
    /act/speech/spoken   ──▶  the done-ack: ok, duration, reason
    /act/speaker/state   ──▶  the device: playing or idle
    /act/speaker/stop    ◀──  barge-in

``/act/speech/chunk`` carries an amplitude, not audio. The samples go
to ``/act/speaker/pcm`` for the driver; this is the envelope a face
uses to open and close a mouth in time with the voice. Two consumers,
two topics, neither paying for the other.

The send box publishes /act/speech/say — the same topic a mind would
use in v5.2. Driving it by hand now is how you find out the wiring
works before there is anything to blame it on.
"""

from __future__ import annotations

import time
from typing import Any

from modules import tts


class VoiceTab:
    """Watch and drive the speech path."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore = QtCore
        self.bus = app.bus

        self._pending: list[tuple[str, str]] = []   # (kind, text)
        self._chunks = 0
        self._peak = 0.0
        self._speaking = False

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)

        # ── say something ──
        self.entry = QtWidgets.QLineEdit()
        self.entry.setPlaceholderText(
            "type something and press enter — publishes /act/speech/say")
        self.entry.returnPressed.connect(self.say)
        send = QtWidgets.QPushButton("Speak")
        send.clicked.connect(self.say)
        stop = QtWidgets.QPushButton("Stop")
        stop.setToolTip("barge-in: drops audio already queued at the device")
        stop.clicked.connect(self.stop)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.entry, 1)
        row.addWidget(send)
        row.addWidget(stop)
        layout.addLayout(row)

        # ── what happened ──
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText(
            "nothing yet.\n\n"
            "If no TTS module is installed this stays empty — the topic "
            "exists, nobody is listening. `python3 main.py --nodes` says "
            "which modules the app actually found.")
        layout.addWidget(self.log, 1)

        self.status = QtWidgets.QLabel("speaker: idle")
        self.status.setStyleSheet("color:#6a6a78;")
        layout.addWidget(self.status)

        # Say so up front rather than leaving an empty log to interpret.
        self._no_module = not tts.available()
        if self._no_module:
            self.status.setText(
                f"no TTS module installed ({tts.PACKAGE}) — typing here "
                f"publishes, nothing answers")

        # The binding says which topics follow the speech path; the
        # tab only decides how to draw them.
        self._watching = tuple(zip(tts.WATCH, (
            self._on_say, self._on_spoken, self._on_chunk, self._on_speaker)))
        for topic, handler in self._watching:
            self.bus.subscribe(topic, handler)

        # Drain onto the GUI thread. Every handler below runs on the
        # bus's delivery thread, and touching a widget from there is a
        # crash that only shows up under load.
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(100)

    # ── driving it ───────────────────────────────────────────────

    def say(self) -> None:
        text = self.entry.text()
        self.entry.clear()
        tts.say(self.bus, text)

    def stop(self) -> None:
        """Barge-in. The binding knows it takes two topics."""
        tts.stop(self.bus)

    # ── bus thread: record only ──────────────────────────────────

    def _stamp(self) -> str:
        return time.strftime("%H:%M:%S")

    def _on_say(self, msg: Any) -> None:
        self._pending.append(("→", f"say  {msg.text!r}"))

    def _on_spoken(self, msg: Any) -> None:
        verdict = "ok" if msg.ok else f"failed: {msg.reason}"
        self._pending.append(("←", f"spoken  {verdict}  {msg.duration_s:.1f}s"))

    def _on_chunk(self, msg: Any) -> None:
        """Amplitude, not audio — the lip-sync envelope.

        Per-chunk log lines would flood; the peak is what a face would
        act on, so that is what is worth showing.
        """
        self._chunks += 1
        self._peak = max(self._peak, float(getattr(msg, "amplitude", 0.0)))

    def _on_speaker(self, msg: Any) -> None:
        self._speaking = msg.state == "playing"
        if msg.state == "idle" and self._chunks:
            self._pending.append(
                ("·", f"{self._chunks} chunks, peak amplitude "
                      f"{self._peak:.2f} — queue drained"))
            self._chunks = self._peak = 0

    # ── GUI thread ───────────────────────────────────────────────

    def _drain(self) -> None:
        while self._pending:
            arrow, text = self._pending.pop(0)
            self.log.appendPlainText(f"{self._stamp()}  {arrow} {text}")
        if self._no_module and not self._chunks and not self._speaking:
            return
        self.status.setText(
            f"speaker: {'playing' if self._speaking else 'idle'}"
            + (f"   chunks: {self._chunks}  peak {self._peak:.2f}"
               if self._chunks else ""))

    def close(self) -> None:
        self._timer.stop()
        for topic, handler in self._watching:
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["VoiceTab"]
