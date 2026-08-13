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

WHICH PIPELINE. The STT module is not one algorithm — it ships several
segmentation strategies, and which one is right depends on the room
rather than on taste: a VAD-closed phrase is the most accurate and the
slowest to commit, a rolling window gives live captions and no wake
word. Burying that in the manifest means editing a file and relaunching
to compare two, so it is a picker. Switching REBUILDS the node, because
the mode is read once when the engine is constructed.

THIS TAB OWNS THE EARS. Running the STT to watch what a microphone
hears is a thing worth doing on its own — no conversation, no mind, no
voice — so the switch is here rather than borrowed from Chat. Chat can
still start them (ticking "Listen" is one click for "I want to talk"),
but turning them OFF belongs to the tab that shows what they do.

Two tabs, one switch, and they cannot disagree: both read the position
back from the supervisor rather than remembering a click. See
`core/audio_switch.py`.

Nothing here imports Whisper. It subscribes, like everything else.
"""

from __future__ import annotations

import time
from typing import Any

from core import audio_switch
from core.module_support import background
from modules import jaeger_whisper_stt as stt


class HearingTab:
    """Watch the microphone and the transcripts it produces."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self.app = app
        self.bus = app.bus

        self._pending: list[str] = []
        self._level = 0.0            # 0..1, written by the bus thread
        self._frames = 0
        self._last_frame_at = 0.0
        self._switches: list[str] = []   # results of a swap, from a thread

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)

        # ── on, and which pipeline ──
        engine = QtWidgets.QHBoxLayout()
        self.power = QtWidgets.QCheckBox("Ears")
        self.power.setToolTip(
            f"start and stop the STT node ({stt.PACKAGE}). The microphone is "
            f"opened only while this is on."
            if stt.available() else f"no STT module installed ({stt.PACKAGE})")
        self.power.setEnabled(audio_switch.available(app)[0])
        self.power.toggled.connect(self._power_toggled)
        engine.addWidget(self.power)
        engine.addSpacing(10)
        engine.addWidget(QtWidgets.QLabel("engine"))
        self.engine = QtWidgets.QComboBox()
        for name, desc in stt.modes():
            self.engine.addItem(name, desc)
        self.engine.setCurrentText(stt.mode(app))
        self.engine.setEnabled(self.engine.count() > 0)
        self.engine.currentTextChanged.connect(self._swap)
        engine.addWidget(self.engine)
        self.engine_note = QtWidgets.QLabel()
        self.engine_note.setStyleSheet("color:#6a6a78;")
        self.engine_note.setWordWrap(True)
        engine.addWidget(self.engine_note, 1)
        layout.addLayout(engine)
        self._describe()

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

    # ── picking a pipeline ───────────────────────────────────────

    def _describe(self) -> None:
        if not self.engine.count():
            self.engine_note.setText(
                f"no STT module installed ({stt.PACKAGE})")
            return
        self.engine_note.setText(str(self.engine.currentData() or ""))

    def _power_toggled(self, on: bool) -> None:
        """Start or stop the ears. Blocks on a model load, so: a thread."""
        if on == audio_switch.state(self.app)[0]:
            return                    # the tick came from _drain re-syncing
        self.power.setEnabled(False)
        self._pending.append(f"ears {'starting' if on else 'stopping'}…")
        background(lambda: audio_switch.switch(self.app, ears=on),
                   self._switches)

    def _swap(self, name: str) -> None:
        """Rebuild the ears on the chosen pipeline, off the GUI thread.

        With the ears OFF this is only a config write and lands
        instantly; with them on it is a stop and a start, which reloads a
        Whisper model — hence the thread and the disabled box.
        """
        self._describe()
        self.engine.setEnabled(False)
        self._pending.append(f"engine → {name}")
        background(lambda: stt.set_mode(self.app, name), self._switches)

    # ── bus thread ───────────────────────────────────────────────

    def _on_audio(self, msg: Any) -> None:
        """Bus thread. The imported module computes the level — see its
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
        while self._switches:
            failed = self._switches.pop(0)
            self.log.appendPlainText(
                f"{stamp}  " + (f"not done — {failed}" if failed
                                else f"ready: {stt.mode(self.app)}"))
            self.engine.setEnabled(bool(self.engine.count()))
            self.power.setEnabled(audio_switch.available(self.app)[0])

        # The ears can be started from the Chat tab too, so the box is
        # read back from the supervisor rather than left where it was
        # clicked. blockSignals, or re-syncing would look like a toggle.
        listening_now = stt.listening(self.app)
        if self.power.isChecked() != listening_now:
            self.power.blockSignals(True)
            self.power.setChecked(listening_now)
            self.power.blockSignals(False)

        self.meter.setValue(int(min(1.0, self._level) * 100))
        self._level *= 0.85

        listening = listening_now
        if not self._frames:
            self.mic_status.setText(
                f"mic: {stt.mode(self.app)}, waiting for /sense/mic/pcm"
                if listening else
                f"mic: off — tick Ears "
                f"({stt.mode(self.app)} is what will start)")
        elif time.monotonic() - self._last_frame_at > 1.0:
            self.mic_status.setText(
                f"mic: STOPPED — {self._frames} frames, then silence")
        else:
            self.mic_status.setText(
                f"mic: live on {stt.mode(self.app)}, {self._frames} frames")

    def close(self) -> None:
        self._timer.stop()
        for topic, handler in self._watching:
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["HearingTab"]
