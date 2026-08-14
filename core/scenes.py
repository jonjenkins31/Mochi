"""Scripted performances — a face, a voice, and waiting for a person.

A scene is a list of steps run against the bus. Four kinds cover
everything the Stage demos need, and the fourth is the one that does not
exist anywhere else:

    FACE    show an expression from the character's own vocabulary
    SAY     speak a line, and WAIT FOR IT TO FINISH
    WAIT    hold for a fixed time
    LISTEN  hold until a person answers, or a timeout passes

WHY THIS IS NOT A MOTION SCRIPT. mscript dispatches to one channel and
has no speech command, so it can animate a character but not make it
talk. A timeline has both channels but only a wall clock — every clip
is pinned to an offset decided before anyone pressed play. Neither can
express "say this, then wait until they answer, however long that
takes", which is the shape of a conversation and of most performances
worth watching.

WHY SAY BLOCKS ON THE DONE-ACK. Synthesis and playback are different
events, and a scene that moves on when synthesis returns talks over
itself. `/act/speech/spoken` is the honest signal; the estimate is only
the fallback for when no voice is running at all, so the scene keeps
roughly correct time on a silent machine instead of racing to the end.

RUNS ON ITS OWN THREAD, never the GUI's, because LISTEN blocks for as
long as a person takes to think.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from jaeger_os import topics

from modules import jaeger_animation as animation
from modules import jaeger_kokoro_tts as tts
from modules import jaeger_whisper_stt as stt

#: Rough speaking pace, for keeping time when nothing is speaking. Only
#: ever used when the done-ack never arrives — a scene on a machine with
#: no voice should still look like a performance rather than a flicker.
_WORDS_PER_SECOND = 2.6
_MIN_SAY_S = 0.8


@dataclass
class Step:
    kind: str                    # face | say | wait | listen
    value: str = ""
    seconds: float = 0.0


@dataclass
class Scene:
    """A named performance, and what it needs to be worth watching."""

    name: str
    description: str
    steps: list[Step] = field(default_factory=list)
    loop: bool = False
    #: True when a step waits on a person. The Stage says so, because a
    #: scene that is waiting looks identical to one that has hung.
    @property
    def interactive(self) -> bool:
        return any(s.kind == "listen" for s in self.steps)


def face(expression: str) -> Step:
    return Step("face", expression)


def say(text: str) -> Step:
    return Step("say", text)


def wait(seconds: float) -> Step:
    return Step("wait", seconds=seconds)


def listen(seconds: float = 10.0) -> Step:
    return Step("listen", seconds=seconds)


class SceneRunner:
    """Play one scene against the bus, off the GUI thread."""

    def __init__(self, app: Any, character: Any,
                 on_event: Callable[[str], None] | None = None) -> None:
        self.app = app
        self.bus = app.bus
        self.character = character
        self._on_event = on_event or (lambda _line: None)
        self._stop = threading.Event()
        self._spoken = threading.Event()
        self._heard = threading.Event()
        self._heard_text = ""
        self._thread: threading.Thread | None = None
        self.scene: Scene | None = None
        self.running = False

    # ── the person's side ────────────────────────────────────────

    def _on_spoken(self, _msg: Any) -> None:
        self._spoken.set()

    def _on_transcript(self, msg: Any) -> None:
        if getattr(msg, "is_final", True):
            self.heard(str(getattr(msg, "text", "")))

    def heard(self, text: str) -> None:
        """A person answered — by voice or by typing.

        Both satisfy a LISTEN, deliberately. A demo that only accepts
        speech cannot be shown on a laptop with no microphone, and the
        scene does not care which way the words arrived.
        """
        text = (text or "").strip()
        if not text:
            return
        self._heard_text = text
        self._heard.set()

    @property
    def last_heard(self) -> str:
        return self._heard_text

    # ── lifecycle ────────────────────────────────────────────────

    def start(self, scene: Scene) -> None:
        self.stop()
        self.scene = scene
        self._stop.clear()
        self.bus.subscribe(tts.SPOKEN, self._on_spoken)
        self.bus.subscribe(stt.TRANSCRIPT, self._on_transcript)
        self.running = True
        self._thread = threading.Thread(
            target=self._run, name=f"scene:{scene.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._heard.set()          # release a LISTEN that is still waiting
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        for topic, handler in ((tts.SPOKEN, self._on_spoken),
                               (stt.TRANSCRIPT, self._on_transcript)):
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass
        self.running = False

    # ── the performance ──────────────────────────────────────────

    def _run(self) -> None:
        scene = self.scene
        try:
            while not self._stop.is_set():
                for step in scene.steps:
                    if self._stop.is_set():
                        return
                    self._perform(step)
                if not scene.loop:
                    return
        finally:
            self.running = False
            self._on_event(f"— {scene.name} ended —")

    def _perform(self, step: Step) -> None:
        if step.kind == "face":
            self._on_event(f"face  {step.value}")
            try:
                animation.play(self.bus, self.character, step.value)
            except Exception as exc:  # noqa: BLE001 — one bad step, not a crash
                self._on_event(f"      ! {exc}")
        elif step.kind == "say":
            self._on_event(f"say   {step.value!r}")
            self._say(step.value)
        elif step.kind == "wait":
            self._stop.wait(timeout=step.seconds)
        elif step.kind == "listen":
            self._listen(step.seconds)

    def _say(self, text: str) -> None:
        """Speak, then wait for the done-ack rather than guessing."""
        self._spoken.clear()
        tts.say(self.bus, text, voice=tts.voice(self.app))
        estimate = max(_MIN_SAY_S, len(text.split()) / _WORDS_PER_SECOND)
        if not tts.audible(self.app):
            # Nothing is going to answer. Hold the estimate so the scene
            # still reads as a performance instead of finishing instantly.
            self._stop.wait(timeout=estimate)
            return
        if not self._spoken.wait(timeout=estimate + 15.0):
            self._on_event("      ! no done-ack — is the voice running?")

    def _listen(self, seconds: float) -> None:
        """Hold until a person answers, or the window closes.

        The pause is the whole point: everything else in a scene is
        decided before it starts, and this is the one step whose length
        the audience chooses.
        """
        self._heard.clear()
        self._heard_text = ""
        self._on_event(f"listen … up to {seconds:.0f}s")
        stt.open_followup(self.app)     # no wake phrase needed mid-scene
        if self._heard.wait(timeout=seconds) and self._heard_text:
            self._on_event(f"heard {self._heard_text!r}")
        else:
            self._on_event("heard nothing")


__all__ = ["Scene", "Step", "SceneRunner", "face", "say", "wait", "listen"]
