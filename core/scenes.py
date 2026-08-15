"""Performances — a face, a voice, and waiting for a person.

A performance is an MSCRIPT, saved in the character's own `mscripts/`
beside every other motion script it owns. It is data, not code: the
MScript Editor opens it, the node graph draws it, and the Stage runs it.

Five commands, and the last is the one that exists nowhere else:

    FACE EXPR[happy]      an expression from the character's OWN
                          vocabulary, so one script suits any pack
                          that declares the same faces
    SAY TXT['...']        speak a line, and WAIT FOR IT TO FINISH
    WAIT D[1.5]           hold for a fixed time
    LISTEN D[10]          hold until a person answers, or time out
    ASK D[20]             hand what was just heard to the MIND, and
                          speak its reply — the improvised beat in an
                          otherwise authored script
    LBL[n] / JMP LBL[n]   loop, exactly as the engine does it

ASK IS THE ONE STEP WHOSE WORDS ARE NOT WRITTEN DOWN. Everything else in
a script is decided by the author; this hands one beat to the model and
speaks whatever comes back. That is what makes "plan the flow, let it
improvise the lines" expressible: the structure stays authored and
reviewable, and only the words vary. It needs no tools — a reply is
text, and text is all a chat model returns.

WHO RUNS WHAT, because there are two readers of this format and that is
deliberate. JaegerAnimation's engine plays the ANIMATION commands —
BITMAP, MEDIA, SPRITE, MATH — and its job ends at frames on a topic;
making it publish speech would break the one rule that engine has. So
the app conducts: this runner reads the same file and dispatches FACE to
the display topic and SAY to the speech topic. The format is shared, the
animation subset is identical, and neither reader has to know about the
other.

WHY NOT A TIMELINE. A timeline has both channels but only a wall clock:
every clip is pinned to an offset chosen before anyone pressed play. It
cannot express "say this, then wait until they answer, however long that
takes" — which is the shape of a conversation, and of most performances
worth watching. A timeline is for a scene whose timing is known; a
performance script is for one that stops for you.

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
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable

from jaeger_os import topics

from core import expressive
from modules import jaeger_agent as mind
from modules import jaeger_animation as animation
from modules import jaeger_kokoro_tts as tts
from modules import jaeger_whisper_stt as stt

#: Rough speaking pace, for keeping time when nothing is speaking. Only
#: ever used when the done-ack never arrives — a scene on a machine with
#: no voice should still look like a performance rather than a flicker.
_WORDS_PER_SECOND = 2.6
_MIN_SAY_S = 0.8

#: Jumps allowed between two steps that take time. A loop with a WAIT,
#: SAY or LISTEN in it resets this every pass and never approaches it; a
#: loop with none would spin this thread at full speed forever.
_MAX_JUMPS_PER_PASS = 64


@dataclass
class Step:
    kind: str                    # face | say | wait | listen | jmp | lbl
    value: str = ""
    seconds: float = 0.0
    label: int | None = None


@dataclass
class Scene:
    """A named performance, loaded from the character's mscripts/."""

    name: str
    description: str
    steps: list[Step] = field(default_factory=list)
    path: Any = None

    @property
    def loop(self) -> bool:
        """A script that jumps backwards runs until something stops it."""
        return any(s.kind == "jmp" for s in self.steps)

    @property
    def interactive(self) -> bool:
        """True when a step waits on a person. The Stage says so, because
        a performance that is waiting looks identical to one that hung."""
        return any(s.kind == "listen" for s in self.steps)


def _quoted(value: str) -> str:
    """`TXT['hello']` keeps its quotes through the arg regex — the
    grammar captures everything up to the bracket. Strip one matched
    pair so a line reads as written."""
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def _label_id(raw: Any) -> int | None:
    """`LBL[1]` and `LBL[1:name]` are the same label — the name is a
    comment, exactly as the engine treats it."""
    try:
        return int(str(raw).split(":", 1)[0].strip())
    except (TypeError, ValueError):
        return None


def load(path: Any) -> Scene:
    """Read a performance from a `.mscript` file.

    Uses the SAME parser the editor and the node graph use, so a script
    that round-trips there runs here — one format, one reader for its
    shape, and no second dialect to drift.
    """
    from interfaces.mscript_editor import parse_mscript, parse_steps

    path = pathlib.Path(path)
    sections = parse_mscript(path.read_text(encoding="utf-8"))
    description = " ".join(
        line.lstrip("! ").strip() for line in sections.get("_header", [])
        if line.strip().startswith("!"))

    steps: list[Step] = []
    for parsed in parse_steps(sections.get("main", [])):
        command, args = parsed.command, parsed.args
        hold = float(args.get("D", 0) or 0)
        if command == "FACE":
            steps.append(Step("face", str(args.get("EXPR", "")), hold))
        elif command == "SAY":
            steps.append(Step("say", _quoted(args.get("TXT", ""))))
        elif command == "WAIT":
            steps.append(Step("wait", seconds=hold))
        elif command == "LISTEN":
            steps.append(Step("listen", seconds=hold or 10.0))
        elif command == "ASK":
            steps.append(Step("ask", _quoted(args.get("TXT", "")),
                              hold or 25.0))
        elif command == "LBL":
            steps.append(Step("lbl", label=_label_id(args.get("LBL"))))
        elif command == "JMP":
            steps.append(Step("jmp", label=_label_id(args.get("LBL"))))
        # Animation commands (BITMAP/MEDIA/SPRITE/MATH) are the ENGINE's
        # half of this format and are skipped here rather than
        # reimplemented — see the module docstring.
    return Scene(name=path.stem.replace("_", " "),
                 description=description or path.name, steps=steps, path=path)


def available(character: Any) -> tuple[Scene, ...]:
    """Every performance in this character's mscripts/, loadable ones only.

    A script with no FACE, SAY or LISTEN is an animation-only motion
    script — the engine's to play, not a performance — so it is left out
    rather than offered as a button that does nothing visible.
    """
    root = pathlib.Path(getattr(character, "root", "") or "")
    found = []
    for path in sorted((root / "mscripts").glob("*.mscript")):
        try:
            scene = load(path)
        except Exception:  # noqa: BLE001 — a broken script is not a broken tab
            continue
        if scene.steps:
            found.append(scene)
    return tuple(found)


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
        self._replied = threading.Event()
        self._reply_text = ""
        self._thread: threading.Thread | None = None
        self.scene: Scene | None = None
        self.running = False

    # ── the person's side ────────────────────────────────────────

    def _on_spoken(self, _msg: Any) -> None:
        self._spoken.set()

    def _on_reply(self, msg: Any) -> None:
        self._reply_text = str(getattr(msg, "text", ""))
        self._replied.set()

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
        self.bus.subscribe(mind.CHAT_REPLY, self._on_reply)
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
        self._replied.set()        # release an ASK that is still waiting
        for topic, handler in ((tts.SPOKEN, self._on_spoken),
                               (stt.TRANSCRIPT, self._on_transcript),
                               (mind.CHAT_REPLY, self._on_reply)):
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass
        self.running = False

    # ── the performance ──────────────────────────────────────────

    def _run(self) -> None:
        """Walk the steps, honouring JMP.

        A program counter rather than a for-loop, because JMP moves it —
        the same shape the engine uses, and the same runaway guard: a
        loop with nothing to wait on would spin this thread at full
        speed forever, so jumps are budgeted between waits.
        """
        scene = self.scene
        labels = {s.label: i for i, s in enumerate(scene.steps)
                  if s.kind == "lbl" and s.label is not None}
        counter = 0
        jumps = 0
        try:
            while not self._stop.is_set() and counter < len(scene.steps):
                step = scene.steps[counter]
                counter += 1
                if step.kind == "lbl":
                    continue
                if step.kind == "jmp":
                    target = labels.get(step.label)
                    if target is None:
                        self._on_event(f"      ! no LBL[{step.label}]")
                        continue
                    jumps += 1
                    if jumps > _MAX_JUMPS_PER_PASS:
                        self._on_event("      ! runaway loop — a loop needs "
                                       "a WAIT, SAY or LISTEN. stopping.")
                        return
                    counter = target
                    continue
                jumps = 0          # anything that takes time resets the budget
                self._perform(step)
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
            if step.seconds:
                # `D` on a FACE holds it, so a script reads as one line
                # per beat instead of alternating face/wait pairs.
                self._stop.wait(timeout=step.seconds)
        elif step.kind == "say":
            self._on_event(f"say   {step.value!r}")
            self._say(step.value)
        elif step.kind == "wait":
            self._stop.wait(timeout=step.seconds)
        elif step.kind == "listen":
            self._listen(step.seconds)
        elif step.kind == "ask":
            self._ask(step.value, step.seconds)

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

    def _ask(self, prompt: str, seconds: float) -> None:
        """Hand a beat to the mind and speak what comes back.

        `TXT` overrides, otherwise it asks about whatever LISTEN just
        heard — which is the shape that makes a scripted conversation
        work: the author writes the turns, the model writes the words.

        Blocks for as long as inference takes, which is why a scene
        runs on its own thread. A model that never answers must not
        strand the performance, so the wait is bounded and the script
        carries on either way.
        """
        question = (prompt or self._heard_text or "").strip()
        if not question:
            self._on_event("ask   nothing to ask about")
            return
        self._on_event(f"ask   {question!r}")
        self._replied.clear()
        self._reply_text = ""
        if not mind.ask(self.bus, question, session=f"scene:{self.scene.name}"):
            self._on_event("      ! no mind installed")
            return
        if not self._replied.wait(timeout=seconds):
            self._on_event("      ! the mind did not answer in time")
            return
        expression, line = expressive.split(
            self._reply_text, self.character.expressions)
        if expression:
            self._on_event(f"face  {expression}   (the mind chose it)")
            try:
                animation.play(self.bus, self.character, expression)
            except Exception:  # noqa: BLE001
                pass
        if line:
            self._say(line)

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


__all__ = ["Scene", "Step", "SceneRunner", "load", "available",
           "compile_timeline", "has_tracks", "track_kind", "TRACK_PREFIX"]


# ── one file, many channels ──────────────────────────────────────
#
# FANUC's split, and the reason this works: a TP program is STORED in
# one form and READ as a listing. Nobody authors the binary. Here the
# listing is the source and a `Timeline` is the compiled artifact the
# scheduler consumes — so a scene and a performance stop being two
# kinds of file and become two things one file can contain.
#
#     [Main start]        the sequential program. Can LISTEN, can loop,
#     [Main end]          can ASK. A program counter, as it always was.
#
#     [Track_eyes start]  a channel on the clock. Every line carries
#     [Track_eyes end]    T[seconds] — when, not what-comes-next.
#
# The section mechanism needed no change: `parse_mscript` has accepted
# arbitrary section names since Mochi 3.0. The capability was already
# in the format and simply unused.

#: A section whose name starts with this is a timeline track. Everything
#: else — Header, Resources, Main, Keyframes — keeps its meaning.
TRACK_PREFIX = "track_"

#: Which bus channel a track feeds, from its name. `Track_eyes` and
#: `Track_face` both mean animation; the suffix is a LABEL for a human
#: reading the listing, not a routing decision, so unknown names fall
#: back to animation rather than refusing to load.
_TRACK_KINDS = {
    "voice": "speech", "speech": "speech", "say": "speech",
    "eyes": "animation", "face": "animation", "anim": "animation",
    "light": "light", "lights": "light",
    "motion": "motion", "servo": "motion", "sound": "sound",
    "cue": "script", "script": "script",
}


def track_kind(section: str) -> str:
    return _TRACK_KINDS.get(section[len(TRACK_PREFIX):].lower(), "animation")


def compile_timeline(path: Any, target: str = "") -> Any:
    """Compile a `.mscript`'s `[Track_*]` sections into a `Timeline`.

    Returns None when the file has no tracks — that is a plain
    performance and belongs to the SceneRunner, not the scheduler.

    Timing comes from `T[seconds]`, absolute from the track's start. A
    track is a clock, so a line says WHEN rather than what-comes-next —
    that is the whole difference from `[Main]`, and it is why both can
    live in one file without either changing meaning.
    """
    from jaeger_os.timeline import Timeline, TimelineClip, TimelineTrack

    from interfaces.mscript_editor import parse_mscript, parse_steps

    path = pathlib.Path(path)
    sections = parse_mscript(path.read_text(encoding="utf-8"))
    tracks = []
    for name, lines in sections.items():
        if not name.startswith(TRACK_PREFIX):
            continue
        clips = []
        for parsed in parse_steps(lines):
            if not parsed.command:
                continue
            args = parsed.args
            at = int(float(args.get("T", 0) or 0) * 1000)
            hold = int(float(args.get("D", 0) or 0) * 1000)
            payload: dict[str, Any] = {}
            if parsed.command == "FACE":
                payload["expression"] = str(args.get("EXPR", ""))
            elif parsed.command == "SAY":
                payload["text"] = _quoted(args.get("TXT", ""))
                if args.get("VOICE"):
                    payload["voice"] = str(args["VOICE"])
            elif parsed.command == "CUE":
                payload["script"] = _quoted(args.get("SRC", ""))
            elif parsed.command == "LIGHT":
                payload["rgb"] = [int(v) for v in
                                  str(args.get("CLR", "0,0,0")).split(",")]
            else:
                payload = {k.lower(): v for k, v in args.items()
                           if k not in ("T", "D")}
            clips.append(TimelineClip(t_offset_ms=at, duration_ms=hold,
                                      payload=payload,
                                      label=str(args.get("LBL", "")) or ""))
        if clips:
            tracks.append(TimelineTrack(
                kind=track_kind(name), target=target,
                name=name[len(TRACK_PREFIX):], clips=clips))
    if not tracks:
        return None
    description = " ".join(
        line.lstrip("! ").strip() for line in sections.get("_header", [])
        if line.strip().startswith("!"))
    return Timeline(name=path.stem.replace("_", " "),
                    description=description, tracks=tracks)


def has_tracks(path: Any) -> bool:
    """Cheap check: does this file want the scheduler or the runner?"""
    from interfaces.mscript_editor import parse_mscript

    try:
        sections = parse_mscript(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return any(name.startswith(TRACK_PREFIX) for name in sections)
