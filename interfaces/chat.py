"""Chat tab — talk to the character, and watch the turn happen.

Every widget here is fed by a topic. Nothing imports a model, a
provider client, or a prompt: the whole integration is two messages.

    /act/chat          ◀──  a turn from you
    /sense/chat        ──▶  the answer
    /sense/agent_state ──▶  thinking / idle / error — what drives the label

The module owns the transcript, the wire format, retries and the
context window, which is why there is no history list in this file and
no prompt assembled anywhere in Mochi. "New conversation" is a new
session id, not a buffer this tab clears — the module keys history by
session, so a fresh id is genuinely a fresh conversation.

MIC AND SPEAKERS ARE OFF. Mochi boots as a messaging LLM: you type, it
answers in the log, and no audio device is opened. Nothing here loads a
Whisper model or warms Kokoro until you ask for it.

POWER IS NOT ROUTING, and the two used to be one checkbox here. They
are different questions:

    is the STT running?          Hearing tab — it owns that node
    is the TTS running?          Voice tab — it owns that node
    should what it hears be
      answered by the mind?      HERE
    should the answer be
      said out loud?             HERE

Running the ears to watch transcripts, or the voice to auction a Kokoro
voice, has nothing to do with holding a conversation, so the switches
that do those things live in the tabs that show them and this tab only
decides what reaches the mind. Ticking a box here still switches the
node on if it is off — that is the "I want to talk to it" path and it
should be one click — but unticking only stops the routing. Turning a
node OFF belongs to the tab that owns it.

All three tabs read their switch position back from the supervisor
rather than remembering the click, which is why the same switch can
appear in two places without them ever disagreeing. See
`core/audio_switch.py`, which is the one thing allowed to move them.

NOT HEARING ITSELF. A voice loop's characteristic failure is the
character answering its own reply, and then answering that, forever.
This tab is where it is prevented, because it is the only thing that
knows both when the speaker is playing and when a transcript is about
to become a turn:

    /act/speaker/state  playing ──▶ pause the ears, drop transcripts
    /act/speaker/state  idle    ──▶ wait out the tail, then reopen

Two more defences live in the engine and are switched on by
`core/voice_modes.py`: the wake phrase, and a self-speech filter fed by
`remember_reply()` after every answer. All three shipped, none were
turned on, and that is exactly why it looped.

WHICH PIPELINE. The mode picker in the header is the point of Mochi —
`assistant` is half duplex with a wake phrase, `chat` is full duplex
with barge-in, and both are the reference scripts in the project root
rather than something invented here.

A CHATBOT, NOT AN AGENT. jaeger-agent can read files and run code;
Mochi asks it not to. See `modules/jaeger_agent.py` for why that is an
environment variable set in main() rather than a setting here.

Like the Voice tab, this works identically whether the module is
installed or not: with one it answers, without it says so.
"""

from __future__ import annotations

import time
from typing import Any

from core import audio_switch, voice_modes
from core.module_support import background
from modules import jaeger_agent as mind
from modules import jaeger_kokoro_tts as tts
from modules import jaeger_whisper_stt as stt


class ChatTab:
    """Drive one conversation and show what the mind is doing."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, _QtGui, QtWidgets = qt
        self._QtCore = QtCore
        self.app = app
        self.bus = app.bus

        self._pending: list[tuple[str, str]] = []   # (speaker, text)
        self._state = "idle"
        self._detail = ""
        self._turn = 0
        self._awaiting_speech = False
        self._switches: list[str] = []   # results of a start/stop, from a thread
        self._switching = 0              # switches still in flight
        # The self-speech gate. `_deaf_until` is monotonic and written by
        # the bus thread; 0.0 means "listening". `inf` while the speaker
        # is actually playing, because we do not know yet how long that
        # will be — the idle message is what converts it to a deadline.
        self._deaf_until = 0.0
        self._ears_paused = False
        # A switch needs both a module to run and a node declared to run
        # it in — sim.toml has neither audio node, so there is nothing to
        # start and the box says so by staying grey.
        self._can_hear, self._can_speak = audio_switch.available(app)
        self.session = "mochi-1"

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QtWidgets.QHBoxLayout()
        self.state = QtWidgets.QLabel()
        self.state.setStyleSheet("color:#8aaad0;")
        header.addWidget(self.state)
        header.addStretch(1)
        # Which voice pipeline. Testing these against a real room is the
        # point of the project, so it is a picker rather than a constant.
        self.mode = QtWidgets.QComboBox()
        for name in voice_modes.names():
            self.mode.addItem(name, voice_modes.describe(name))
        self.mode.setCurrentText(voice_modes.current(app))
        self.mode.setToolTip(voice_modes.describe(voice_modes.current(app)))
        self.mode.currentTextChanged.connect(self._mode_chosen)
        header.addWidget(QtWidgets.QLabel("pipeline"))
        header.addWidget(self.mode)
        # Two ROUTING switches, both off. Mirrored into plain bools
        # because both are read from the BUS thread — a reply arriving, a
        # transcript landing — and that thread has no business reading a
        # widget.
        self._mic_on = False
        self._speak_replies = False
        self.mic = QtWidgets.QCheckBox("Listen")
        self.mic.setToolTip(
            "send what the ears hear to the mind. Ticking this starts them "
            "if they are off; the Hearing tab is where they get turned off."
            if stt.available() else f"no STT module installed ({stt.PACKAGE})")
        self.mic.toggled.connect(self._mic_toggled)
        header.addWidget(self.mic)
        self.speak = QtWidgets.QCheckBox("Speak replies")
        self.speak.setToolTip(
            "say each reply out loud. Ticking this starts the voice if it is "
            "off; the Voice tab is where it gets turned off."
            if tts.available() else f"no TTS module installed ({tts.PACKAGE})")
        self.speak.toggled.connect(self._speak_toggled)
        header.addWidget(self.speak)
        # What is actually RUNNING, which the boxes above no longer say.
        self.power = QtWidgets.QLabel()
        self.power.setStyleSheet("color:#6a6a78;")
        header.addWidget(self.power)
        clear = QtWidgets.QPushButton("New conversation")
        clear.clicked.connect(self.new_conversation)
        header.addWidget(clear)
        layout.addLayout(header)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        layout.addWidget(self.log, 1)

        row = QtWidgets.QHBoxLayout()
        self.entry = QtWidgets.QLineEdit()
        self.entry.returnPressed.connect(self.send)
        self.send_button = QtWidgets.QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.entry, 1)
        row.addWidget(self.send_button)
        layout.addLayout(row)

        self._no_module = not mind.available()
        if self._no_module:
            # Say it up front rather than leaving an empty log to interpret.
            self.entry.setEnabled(False)
            self.send_button.setEnabled(False)
            self.entry.setPlaceholderText("no mind module installed")
            self.log.setPlainText(
                f"No mind module is installed ({mind.PACKAGE}).\n\n"
                f"    pip install jaeger-agent\n\n"
                f"or re-run ./setup.sh, which prefers a sibling checkout. "
                f"`python3 main.py --nodes` says which modules the app "
                f"actually found.")
        else:
            self.entry.setPlaceholderText(
                "say something and press enter — publishes /act/chat")
            self.log.setPlaceholderText("nothing yet.")

        # The imported module says which topics follow one turn; the tab
        # only decides how to draw them. The speech done-ack is in here
        # too: speaking is a side effect of a reply, so a failure has
        # nowhere else to surface and would otherwise just be silence.
        # The transcript is the other direction — heard speech becoming a
        # turn — and is subscribed unconditionally: the ears not running
        # is already "no messages", so a second gate would be a way for
        # the switch and the subscription to disagree.
        self._watching = tuple(zip(mind.WATCH, (
            self._on_said, self._on_reply, self._on_state))) + (
            (tts.SPOKEN, self._on_spoken),
            (tts.SPEAKER, self._on_speaker),
            (stt.TRANSCRIPT, self._on_transcript))
        for topic, handler in self._watching:
            self.bus.subscribe(topic, handler)

        # Drain onto the GUI thread. Every handler below runs on the
        # bus's delivery thread, and touching a widget from there is a
        # crash that only shows up under load.
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(100)
        self._refresh_state()

    # ── driving it ───────────────────────────────────────────────

    def send(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        if mind.ask(self.bus, text, session=self.session):
            self.entry.clear()

    def _mic_toggled(self, checked: bool) -> None:
        """Route what the ears hear to the mind — and start them if off.

        One click for "I want to talk to it". Unticking stops the
        routing and leaves the ears running, because someone may be
        watching transcripts in the Hearing tab and that is where the
        node gets switched off.
        """
        self._mic_on = bool(checked)
        if checked and not audio_switch.state(self.app)[0]:
            self._switch(ears=True, what="ears")

    def _speak_toggled(self, checked: bool) -> None:
        self._speak_replies = bool(checked)
        if checked and not audio_switch.state(self.app)[1]:
            self._switch(voice=True, what="voice")

    def _mode_chosen(self, name: str) -> None:
        """Swap the whole pipeline.

        Every setting a mode carries is read when a node is BUILT, so a
        live switch is a rebuild of whatever is currently running — the
        same shape as swapping the STT engine in the Hearing tab.
        """
        voice_modes.apply(self.app, name)
        self.mode.setToolTip(voice_modes.describe(name))
        self._append("·", f"pipeline: {name} — {voice_modes.describe(name)}")
        unsupported = voice_modes.warning(name)
        if unsupported:
            self._append("·", unsupported)
        if any(audio_switch.state(self.app)):
            self._switch(what=f"pipeline {name}", restart=True)

    def _switch(self, *, ears: bool | None = None, voice: bool | None = None,
                what: str = "audio", restart: bool = False) -> None:
        """Move the audio stack, off the GUI thread.

        Starting either engine loads a model and rebuilds the shared
        driver, so the work goes to a thread — otherwise a second click
        arrives while the first start is still opening a device, and the
        supervisor is asked to stop something that never finished
        starting.
        """
        self._switching += 1
        self._append("·", f"{what} starting…")
        background(
            lambda: audio_switch.switch(self.app, ears=ears, voice=voice,
                                        restart=restart),
            self._switches)

    def new_conversation(self) -> None:
        """A new session id — the module keys its transcript by that.

        Clearing the log alone would only hide the history; the model
        would still remember it. This forgets.
        """
        self._turn += 1
        self.session = f"mochi-{self._turn + 1}"
        self.log.clear()
        if not self._no_module:
            self._append("·", f"new conversation ({self.session})")

    # ── bus thread: record only ──────────────────────────────────

    def _on_said(self, msg: Any) -> None:
        """The turn as it goes OUT, echoed from the topic rather than
        from send(). Costs nothing and means a turn that arrives some
        other way — an STT transcript routed here, another surface —
        shows up in this log too, instead of a reply to a question the
        operator never sees."""
        self._pending.append(("you", str(getattr(msg, "text", ""))))

    def _on_reply(self, msg: Any) -> None:
        text = str(getattr(msg, "text", ""))
        self._pending.append(("mochi", text))
        if self._speak_replies:
            # Shut the ears BEFORE asking for audio, not when the device
            # reports playing — synthesis and playback are two events and
            # the first syllable lands between them.
            if voice_modes.setting(self.app, "pause_mic_while_speaking"):
                self._deaf_until = float("inf")
                if not self._ears_paused:
                    self._ears_paused = stt.pause(self.app, True)
            # And tell the engine what we are about to say, so its own
            # self-speech filter can drop a close match to it. The
            # backstop for whatever leaks past the pause window.
            stt.remember_reply(self.app, text)
            # Publishing from the bus thread is fine — it is a queue
            # hand-off, not a widget.
            self._awaiting_speech = True
            tts.say(self.bus, text, voice=tts.voice(self.app))

    def _on_spoken(self, msg: Any) -> None:
        """Say so when a reply was asked for out loud and did not arrive.

        Synthesis can succeed while nothing plays: Kokoro publishes PCM
        to /act/speaker/pcm and the audio_io driver is what drains it.
        With no driver running you get a `drain timeout` here and pure
        silence everywhere else, which reads as "the checkbox is broken".
        """
        if not self._awaiting_speech:
            return                       # not ours — the Voice tab's
        self._awaiting_speech = False
        if not getattr(msg, "ok", True):
            self._pending.append(
                ("·", f"not spoken — {getattr(msg, 'reason', 'unknown')}. "
                      f"Is the audio_io driver running? `python3 main.py "
                      f"--nodes`, and note sim.toml starts no audio at all."))

    def _on_speaker(self, msg: Any) -> None:
        """The speaker started or stopped — the ears follow it.

        Bus thread. Pausing the ears is the one defence that cannot be
        fooled by a good imitation of what we just said, because the
        audio never reaches the VAD at all. `reopen_after_s` covers the
        gap the device leaves: the VAD's hangover is 700ms and it pads
        250ms more, so a phrase closing right after playback can still
        be holding the reply's tail.
        """
        if not voice_modes.setting(self.app, "pause_mic_while_speaking"):
            return
        if str(getattr(msg, "state", "")) == "playing":
            self._deaf_until = float("inf")
            if not self._ears_paused:
                self._ears_paused = stt.pause(self.app, True)
        else:
            self._deaf_until = time.monotonic() + float(
                voice_modes.setting(self.app, "reopen_after_s", 1.0))

    def _hearing_ourselves(self) -> bool:
        return time.monotonic() < self._deaf_until

    def _on_transcript(self, msg: Any) -> None:
        """Heard speech becomes a turn — the same turn typing produces.

        Finals only. The streaming pipelines publish `is_final=False`
        while you are still talking, and sending those would ask the mind
        a question three times before the sentence ends.

        The deaf window is checked HERE as well as at the engine, and
        deliberately: unpausing is a call into another thread's object,
        so there is a window where the ears are open again but the last
        phrase they closed still belongs to us. Dropping it costs a
        syllable of a turn nobody started; keeping it costs the loop.
        """
        if not self._mic_on or not getattr(msg, "is_final", True):
            return
        text = str(getattr(msg, "text", ""))
        if self._hearing_ourselves():
            self._pending.append(("·", f"ignored while speaking: {text!r}"))
            return
        mind.ask(self.bus, text, session=self.session)

    def _on_state(self, msg: Any) -> None:
        self._state = str(getattr(msg, "state", "idle"))
        self._detail = str(getattr(msg, "detail", "") or "")

    # ── GUI thread ───────────────────────────────────────────────

    def _append(self, speaker: str, text: str) -> None:
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {speaker}: {text}")

    def _drain(self) -> None:
        while self._pending:
            speaker, text = self._pending.pop(0)
            self._append(speaker, text)
        while self._switches:
            failed = self._switches.pop(0)
            self._switching -= 1
            if failed:
                self._append("·", f"not switched — {failed}")
        # Reopen the ears once the reply has finished and its tail has
        # passed. Done on this timer rather than from the bus thread so
        # the deadline is checked even if the speaker never sends
        # another message — an idle device is silent in both senses.
        if self._ears_paused and not self._hearing_ourselves():
            self._ears_paused = not stt.pause(self.app, False)
            if not self._ears_paused:
                # The reply is over and you were just spoken to, so the
                # next thing you say does not need the wake phrase — a
                # conversation should not require "hey mochi" in front
                # of every sentence. No-op in a mode with no wake gate.
                stt.open_followup(self.app)
        self._refresh_switches()
        self._refresh_state()

    def _refresh_switches(self) -> None:
        """Say what is RUNNING, which the routing boxes no longer imply.

        The boxes are this tab's intent and stay where they were put.
        The nodes are the truth and can move from another tab, so the
        label reads them back from the supervisor every tick — that is
        also what makes the same switch safe to show in three places.
        """
        ears, voice = audio_switch.state(self.app)
        self.mic.setEnabled(self._can_hear)
        self.speak.setEnabled(self._can_speak)
        if not (self._can_hear or self._can_speak):
            self.power.setText("no audio in this manifest")
            return
        busy = " · switching…" if self._switching else ""
        self.power.setText(
            f"ears: {'on' if ears else 'off'}   "
            f"voice: {'on' if voice else 'off'}{busy}")

    def _refresh_state(self) -> None:
        if self._no_module:
            self.state.setText(f"mind: not installed ({mind.PACKAGE})")
            return
        detail = f"  ({self._detail})" if self._detail else ""
        self.state.setText(f"mind: {self._state}{detail}")
        # The module answers one turn at a time and replies "(busy…)" to
        # anything sent meanwhile, so the button says that instead.
        thinking = self._state == "thinking"
        self.send_button.setEnabled(not thinking)
        self.send_button.setText("Thinking…" if thinking else "Send")

    def close(self) -> None:
        self._timer.stop()
        for topic, handler in self._watching:
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["ChatTab"]
