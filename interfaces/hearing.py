"""Hearing tab — what the microphone hears, and what the STT made of it.

    /sense/mic/pcm          ──▶  the level meter: is the mic ALIVE?
    /sense/stt/speech_start ──▶  the VAD decided you started talking
    /sense/stt/transcript   ──▶  what it thinks you said

The level meter is the useful part and it is why this tab is worth
having. "The agent cannot hear me" has three very different causes —
no audio driver, a muted device, or an STT that is not running — and
they are indistinguishable from a log of transcripts. A moving meter
with no transcripts says the mic is fine and the STT is not; a still
meter says stop debugging the STT.

Nothing here imports Whisper. It subscribes, like everything else.
"""

from __future__ import annotations

import time
from typing import Any

from modules import stt


class HearingTab:
    """Watch the microphone and the transcripts it produces."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self.bus = app.bus

        self._pending: list[str] = []
        self._level = 0.0            # 0..1, written by the bus thread
        self._frames = 0
        self._last_frame_at = 0.0

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)

        self.meter = QtWidgets.QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(14)
        self.mic_status = QtWidgets.QLabel("mic: waiting for /sense/mic/pcm")
        self.mic_status.setStyleSheet("color:#6a6a78;")

        layout.addWidget(QtWidgets.QLabel("microphone"))
        layout.addWidget(self.meter)
        layout.addWidget(self.mic_status)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText(
            "nothing heard yet.\n\n"
            "A moving meter with no transcripts means the microphone is "
            "fine and the STT is not running. A still meter means stop "
            "debugging the STT — check `python3 main.py --nodes` for the "
            "audio driver.")
        layout.addWidget(self.log, 1)

        self._watching = tuple(zip(stt.WATCH, (
            self._on_audio, self._on_speech_start, self._on_transcript)))
        for topic, handler in self._watching:
            self.bus.subscribe(topic, handler)

        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(50)        # meter wants to look live

    # ── bus thread ───────────────────────────────────────────────

    def _on_audio(self, msg: Any) -> None:
        """Bus thread. The binding computes the level — see its
        docstring for why that happens here and not on the GUI."""
        self._frames += 1
        self._last_frame_at = time.monotonic()
        # Decay, so the bar falls smoothly instead of flickering.
        self._level = max(stt.frame_level(msg) * 3.0, self._level * 0.8)

    def _on_speech_start(self, msg: Any) -> None:
        self._pending.append("● speech started")

    def _on_transcript(self, msg: Any) -> None:
        self._pending.append(f"“{msg.text}”")

    # ── GUI thread ───────────────────────────────────────────────

    def _drain(self) -> None:
        stamp = time.strftime("%H:%M:%S")
        while self._pending:
            self.log.appendPlainText(f"{stamp}  {self._pending.pop(0)}")

        self.meter.setValue(int(min(1.0, self._level) * 100))
        self._level *= 0.85

        if not self._frames:
            self.mic_status.setText("mic: waiting for /sense/mic/pcm")
        elif time.monotonic() - self._last_frame_at > 1.0:
            self.mic_status.setText(
                f"mic: STOPPED — {self._frames} frames, then silence")
        else:
            self.mic_status.setText(f"mic: live, {self._frames} frames")

    def close(self) -> None:
        self._timer.stop()
        for topic, handler in self._watching:
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["HearingTab"]
