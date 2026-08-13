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

WHICH VOICE. Kokoro has one synthesis path and many voices, which is
the mirror image of the Hearing tab: there the choice is a PIPELINE and
costs a node rebuild, here it is a string that rides the request and
costs nothing. So this picker applies on the next thing said — no
restart, no reload — and the chat replies use the same choice, because
both read it from the manifest's config slice rather than from a widget.

THIS TAB OWNS THE VOICE. Trying a Kokoro voice, or checking that the
speech path works at all, has nothing to do with holding a conversation
— so the switch is here rather than borrowed from Chat. Chat can start
it (ticking "Speak replies" is one click), but turning it OFF belongs
to the tab that drives it. Both read the position back from the
supervisor, so they cannot disagree. See `core/audio_switch.py`.
"""

from __future__ import annotations

import time
from typing import Any

from core import audio_switch
from core.module_support import background
from modules import jaeger_kokoro_tts as tts


class VoiceTab:
    """Watch and drive the speech path."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore = QtCore
        self.app = app
        self.bus = app.bus

        self._pending: list[tuple[str, str]] = []   # (kind, text)
        self._switches: list[str] = []   # results of a start/stop, from a thread
        self._chunks = 0
        self._peak = 0.0
        self._speaking = False

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)

        # ── on, and which voice ──
        picker = QtWidgets.QHBoxLayout()
        self.power = QtWidgets.QCheckBox("Voice")
        self.power.setToolTip(
            f"start and stop the TTS node ({tts.PACKAGE}). Warming Kokoro is "
            f"~8s, which is why it is not on by default."
            if tts.available() else f"no TTS module installed ({tts.PACKAGE})")
        self.power.setEnabled(audio_switch.available(app)[1])
        self.power.toggled.connect(self._power_toggled)
        picker.addWidget(self.power)
        picker.addSpacing(10)
        picker.addWidget(QtWidgets.QLabel("voice"))
        self.voice = QtWidgets.QComboBox()
        for vid, desc in tts.voices():
            self.voice.addItem(vid, desc)
        # Editable: the module's list is curated, not a whitelist — Kokoro
        # accepts ids that are not on it, and refusing them here would be
        # this app deciding what the engine supports.
        self.voice.setEditable(True)
        self.voice.setCurrentText(tts.voice(app) or self.voice.currentText())
        self.voice.setEnabled(bool(self.voice.count()))
        self.voice.currentTextChanged.connect(self._voice_chosen)
        picker.addWidget(self.voice)
        self.voice_note = QtWidgets.QLabel()
        self.voice_note.setStyleSheet("color:#6a6a78;")
        self.voice_note.setWordWrap(True)
        picker.addWidget(self.voice_note, 1)
        layout.addLayout(picker)
        self._voice_chosen(self.voice.currentText())

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
        self.status.setText(self._idle_status())

        # The imported module says which topics follow the speech path; the
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

    def _power_toggled(self, on: bool) -> None:
        """Start or stop the voice. Warming Kokoro blocks, so: a thread."""
        if on == audio_switch.state(self.app)[1]:
            return                    # the tick came from _drain re-syncing
        self.power.setEnabled(False)
        self._pending.append(("·", f"voice {'starting' if on else 'stopping'}…"))
        background(lambda: audio_switch.switch(self.app, voice=on),
                   self._switches)

    def _voice_chosen(self, name: str) -> None:
        """Record the choice where both this tab and Chat read it."""
        tts.set_voice(self.app, name)
        index = self.voice.findText(name)
        self.voice_note.setText(
            str(self.voice.itemData(index)) if index >= 0
            else (f"not on {tts.PACKAGE}'s list — Kokoro decides"
                  if self.voice.count() else
                  f"no TTS module installed ({tts.PACKAGE})"))

    def say(self) -> None:
        text = self.entry.text()
        self.entry.clear()
        tts.say(self.bus, text, voice=tts.voice(self.app))

    def stop(self) -> None:
        """Barge-in. The imported module knows it takes two topics."""
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

    def _idle_status(self) -> str:
        """Why nothing is happening — the three reasons are different.

        No module, module present but its node stopped, and idle-and-
        ready all look identical from the log, and only the middle one
        has an action attached to it.
        """
        if self._no_module:
            return (f"no TTS module installed ({tts.PACKAGE}) — typing here "
                    f"publishes, nothing answers")
        if not tts.audible(self.app):
            return ("voice off — tick Voice. Typing here still publishes "
                    "/act/speech/say; nothing is listening for it.")
        return "speaker: idle"

    def _drain(self) -> None:
        while self._pending:
            arrow, text = self._pending.pop(0)
            self.log.appendPlainText(f"{self._stamp()}  {arrow} {text}")
        while self._switches:
            failed = self._switches.pop(0)
            if failed:
                self.log.appendPlainText(f"{self._stamp()}  · not done — {failed}")
            self.power.setEnabled(audio_switch.available(self.app)[1])

        # The voice can be started from the Chat tab too, so the box is
        # read back from the supervisor rather than left where it was
        # clicked. blockSignals, or re-syncing would look like a toggle.
        audible = tts.audible(self.app)
        if self.power.isChecked() != audible:
            self.power.blockSignals(True)
            self.power.setChecked(audible)
            self.power.blockSignals(False)

        if not self._chunks and not self._speaking:
            self.status.setText(self._idle_status())
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
