"""The Director — one authoritative clock for a show.

A `TimelineRunner` starts, runs and stops. That is a fire-and-forget
scheduler and it is the right shape for "play this cue". It is the
wrong shape for AUTHORING, where the loop is: play a bit, stop, move
the playhead back three seconds, watch it again.

    play      pause      resume     stop
    seek(ms)  range(a,b) loop       preroll

WHAT THE PLAYHEAD IS. `position_ms` is the truth and everything else
derives from it. Paused, it holds; playing, it is wall clock minus the
time spent paused, plus wherever the last seek put it. Every event in
the show is scheduled against that one number, which is the whole
reason a seek can be exact rather than approximate.

SEEK REBUILDS, IT DOES NOT REWIND. Moving the playhead re-derives which
events are still ahead of it and starts from there. Nothing is
un-published — a cue that already fired has already been seen — so
seeking backwards re-fires the cues in the new region. That is what an
editor does, and it is why scrubbing a show with speech in it talks
over itself; the answer is to render dialogue to audio and let the
transport own it, which is the next piece and not this one.

WHAT IT CANNOT DO, said plainly. The timeline half seeks exactly. The
`[Main]` program half is REACTIVE — it can branch, loop and stop for a
person — and a program counter has no wall-clock position to seek to.
So a Director seek restarts the program from the top or leaves it
alone; it cannot put it halfway through. Pretending otherwise is how a
transport lies to an operator.
"""

from __future__ import annotations

import pathlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from jaeger_os import topics
from jaeger_os.timeline import Timeline

try:                                    # the scheduler's own list
    from jaeger_os.timeline.runner import DISPATCHED as _SCHEDULER_KINDS
except ImportError:                     # older JaegerOS
    _SCHEDULER_KINDS = frozenset({"animation", "speech"})

#: What THIS transport can play, which is more than the fire-and-forget
#: scheduler. `light` and `sound` need no hardware on a machine with
#: none: a light is a virtual stage lamp that tints the picture, and a
#: sound is a file down the same speaker path speech already uses.
#: `motion` and `script` stay out — one wants a servo bus and the other
#: is a reactive program the Conductor owns.
DISPATCHED = _SCHEDULER_KINDS | {"light", "sound"}

#: How often the transport reports where it is. 20/s is smooth enough
#: for a playhead and cheap enough to leave on.
TICK_S = 0.05

#: Transport states, and the only ones. `prerolling` is separate from
#: `playing` because an operator needs to see the countdown as a state
#: rather than as a negative position.
IDLE, PREROLL, PLAYING, PAUSED, COMPLETE = (
    "idle", "prerolling", "playing", "paused", "complete")


@dataclass(order=True)
class Cue:
    """One scheduled thing, flattened out of the tracks.

    Sorted by time, so a seek is a bisect rather than a scan of every
    track — and so two cues at the same instant fire in track order,
    which is what an author sees in the file.
    """

    at_ms: int
    order: int
    kind: str = field(compare=False)
    target: str = field(compare=False)
    track: str = field(compare=False)
    clip: Any = field(compare=False)


def cues(timeline: Timeline) -> list[Cue]:
    """Every clip in the show, in time order."""
    out: list[Cue] = []
    for index, track in enumerate(timeline.tracks):
        for clip in track.clips:
            out.append(Cue(int(clip.t_offset_ms), index, track.kind,
                           track.target or "", track.name or track.kind, clip))
    out.sort()
    return out


def duration_of(timeline: Timeline) -> int:
    """How long the show is, from its own clips if it did not say.

    A compiled mscript leaves `duration_ms` at 0 — the author wrote
    cues, not a length — and a transport with no end has no scrub bar.
    """
    if timeline.duration_ms:
        return int(timeline.duration_ms)
    return max((int(c.t_offset_ms + c.duration_ms)
                for t in timeline.tracks for c in t.clips), default=0)


class Director:
    """Transport for one show. Owns the clock; dispatches on the beat."""

    def __init__(self, app: Any, timeline: Timeline | None = None, *,
                 on_tick: Callable[[str, int, int], None] | None = None,
                 on_event: Callable[[str], None] | None = None) -> None:
        self.app = app
        self.bus = app.bus
        self._on_tick = on_tick or (lambda _s, _p, _d: None)
        self._on_event = on_event or (lambda _line: None)

        self.timeline: Timeline | None = None
        self.cues: list[Cue] = []
        self.duration_ms = 0
        self.state = IDLE
        self.loop = False
        self.preroll_ms = 0
        #: The loop/work region. `None` means the whole show, which is
        #: different from a region that happens to span it — clearing
        #: the region has to be expressible.
        self.region: tuple[int, int] | None = None
        #: Set while the playhead is being dragged. Rendered lines play
        #: from an offset and are fine; UNRENDERED ones would have to be
        #: re-synthesised from the top, which is the talking-over-itself
        #: problem, so they are held instead.
        self.scrubbing = False
        #: The virtual stage light: (r, g, b) and how strongly it tints.
        #: There is no lamp on this machine, so the light IS the wash
        #: over the picture — which is what a lighting cue was always
        #: for, and is now visible in the preview and in the export.
        self.light: tuple[int, int, int] | None = None
        self.light_level = 0.35

        self._origin = 0.0          # wall clock at position 0
        self._held_ms = 0           # position while paused
        self._next = 0              # index into `cues`
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.RLock()
        if timeline is not None:
            self.load(timeline)

    # ── loading ──────────────────────────────────────────────────

    def load(self, timeline: Timeline) -> None:
        self.stop()
        self.timeline = timeline
        self.cues = cues(timeline)
        self.duration_ms = duration_of(timeline)
        self.region = None
        self._held_ms = 0
        self._next = 0
        self.state = IDLE
        for name, kind in self.unsupported():
            self._on_event(f"! track {name!r} ({kind}) is scheduled but "
                           f"nothing plays it — no {kind} node is wired")
        self._report()

    def unsupported(self) -> list[tuple[str, str]]:
        """Tracks with no dispatcher, so a UI can grey them out rather
        than draw cues that will not fire."""
        if self.timeline is None:
            return []
        return [(t.name or t.kind, t.kind) for t in self.timeline.tracks
                if t.kind not in DISPATCHED and t.clips]

    # ── the playhead ─────────────────────────────────────────────

    @property
    def position_ms(self) -> int:
        with self._lock:
            if self.state in (PLAYING, PREROLL):
                return max(0, int((time.perf_counter() - self._origin) * 1000))
            return self._held_ms

    @property
    def start_ms(self) -> int:
        return self.region[0] if self.region else 0

    @property
    def end_ms(self) -> int:
        return self.region[1] if self.region else self.duration_ms

    def set_region(self, start_ms: int | None, end_ms: int | None = None
                   ) -> None:
        """The work area. `set_region(None)` clears it."""
        if start_ms is None:
            self.region = None
            return
        a, b = int(start_ms), int(end_ms if end_ms is not None
                                  else self.duration_ms)
        self.region = (max(0, min(a, b)), max(a, b))

    # ── transport ────────────────────────────────────────────────

    def play(self, from_ms: int | None = None) -> None:
        """Start, or resume. `from_ms` seeks first."""
        if self.timeline is None:
            return
        if self.state == PAUSED and from_ms is None:
            return self.resume()
        self.stop(quiet=True)
        self._seek_to(self.start_ms if from_ms is None else int(from_ms))
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="director")
        self._thread.start()

    def pause(self) -> None:
        with self._lock:
            if self.state not in (PLAYING, PREROLL):
                return
            self._held_ms = self.position_ms
            self.state = PAUSED
        self._wake.set()
        self._report()

    def resume(self) -> None:
        with self._lock:
            if self.state != PAUSED:
                return
            self._origin = time.perf_counter() - self._held_ms / 1000.0
            self.state = PLAYING
        self._wake.set()
        self._report()

    def toggle(self) -> None:
        """The space bar. Whatever it is doing, do the other thing."""
        if self.state == PLAYING:
            self.pause()
        elif self.state == PAUSED:
            self.resume()
        else:
            self.play()

    def seek(self, position_ms: int) -> None:
        """Move the playhead. Exact, and legal while playing or stopped.

        Re-derives which cues are ahead rather than replaying history —
        so seeking back over a cue will fire it again, which is what an
        editor does and what a transport must not hide.
        """
        was = self.state
        with self._lock:
            self._seek_to(position_ms)
            if was == PLAYING:
                self._origin = time.perf_counter() - self._held_ms / 1000.0
                self.state = PLAYING
        self._wake.set()
        self._report()

    def resume_under_playhead(self) -> None:
        """Play the audio the playhead is standing IN THE MIDDLE of.

        Without this, seeking into a sentence gives silence until the
        next cue — the show looks like it stopped talking. With a
        rendered file the right answer is obvious: start it partway
        through, which is what any editor does.
        """
        now = self.position_ms
        for cue in self.cues:
            if cue.kind != "speech":
                continue
            payload = cue.clip.payload or {}
            end = cue.at_ms + int(payload.get("rendered_ms",
                                              cue.clip.duration_ms))
            if cue.at_ms <= now < end and payload.get("audio"):
                self._speak(cue, payload, into_ms=now - cue.at_ms)
                return

    def _seek_to(self, position_ms: int) -> None:
        target = max(0, min(int(position_ms), max(0, self.duration_ms)))
        self._held_ms = target
        self._origin = time.perf_counter() - target / 1000.0
        self._next = 0
        while self._next < len(self.cues) and self.cues[self._next].at_ms < target:
            self._next += 1
        found = self.light_at(target)
        if found is not None:
            self.light, self.light_level = found
        if self.state in (COMPLETE, IDLE):
            self.state = PAUSED if self.state == COMPLETE else IDLE

    def stop(self, quiet: bool = False) -> None:
        self._stop.set()
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        with self._lock:
            if self.state in (PLAYING, PREROLL, PAUSED):
                self._held_ms = self.position_ms if self.state != PAUSED \
                    else self._held_ms
            self.state = IDLE if self.state != COMPLETE else COMPLETE
        try:
            self.bus.publish(topics.DisplayStop())
        except Exception:  # noqa: BLE001
            pass
        if not quiet:
            self._report()

    # ── the loop ─────────────────────────────────────────────────

    def _run(self) -> None:
        if self.preroll_ms > 0:
            with self._lock:
                self.state = PREROLL
            self._report()
            # Counted from the playhead so the countdown is visible as
            # negative time, then the show starts exactly at t=start.
            deadline = time.perf_counter() + self.preroll_ms / 1000.0
            while not self._stop.is_set() and time.perf_counter() < deadline:
                self._report()
                self._wake.wait(timeout=TICK_S)
                self._wake.clear()
            with self._lock:
                self._origin = time.perf_counter() - self._held_ms / 1000.0
        with self._lock:
            if self.state != PAUSED:
                self.state = PLAYING
        self._report()

        while not self._stop.is_set():
            if self.state == PAUSED:
                self._wake.wait(timeout=TICK_S)
                self._wake.clear()
                self._report()
                continue
            now = self.position_ms
            while (self._next < len(self.cues)
                   and self.cues[self._next].at_ms <= now):
                cue = self.cues[self._next]
                self._next += 1
                if cue.at_ms <= self.end_ms:
                    self._fire(cue)
            if now >= self.end_ms:
                if self.loop:
                    self.seek(self.start_ms)
                    continue
                break
            self._report()
            self._wake.wait(timeout=TICK_S)
            self._wake.clear()

        with self._lock:
            if not self._stop.is_set():
                self._held_ms = self.end_ms
                self.state = COMPLETE
        self._report()

    def _speak(self, cue: Cue, payload: dict, into_ms: int = 0) -> None:
        """A line: rendered audio if it has any, live TTS if not.

        RENDERED IS THE POINT. A file can start `into_ms` from its
        beginning, so scrubbing into the middle of a sentence is a byte
        offset rather than a re-synthesis — and seeking backwards stops
        making the show talk over itself, because nothing is asked to
        say anything twice.

        Live TTS stays as the fallback so an unrendered show still
        plays; it simply cannot be scrubbed cleanly, which is the
        difference the render pass buys.
        """
        from core import dialogue

        audio = str(payload.get("audio", ""))
        if audio and pathlib.Path(audio).is_file():
            try:
                pcm, rate = dialogue.read(pathlib.Path(audio))
                pcm = dialogue.slice_ms(pcm, rate, into_ms)
                if pcm:
                    self.bus.publish(topics.AudioOutFrame(
                        samples=pcm, sample_rate=rate, channels=1,
                        node_id=cue.target))
                return
            except Exception as exc:  # noqa: BLE001
                self._on_event(f"! {cue.track}: {exc}")
        if self.scrubbing:
            return          # never synthesise live while scrubbing
        self.bus.publish(topics.SpeechCommand(
            text=str(payload.get("text", "")),
            voice=str(payload.get("voice", "")),
            node_id=cue.target))

    def _sound(self, cue: Cue, payload: dict, into_ms: int = 0) -> None:
        """A sound effect: a file, down the speaker path speech uses.

        No new node and no hardware — `/act/speaker/pcm` already has a
        consumer, and a wav is a wav. Plays from an offset for the same
        reason a rendered line does, so scrubbing works on effects too.
        """
        from core import dialogue

        path = pathlib.Path(str(payload.get("file", "")))
        if not path.is_absolute():
            path = pathlib.Path.cwd() / path
        if not path.is_file():
            self._on_event(f"! {cue.track}: no such sound {path.name}")
            return
        try:
            pcm, rate = dialogue.read(path)
            pcm = dialogue.slice_ms(pcm, rate, into_ms)
            if pcm:
                self.bus.publish(topics.AudioOutFrame(
                    samples=pcm, sample_rate=rate, channels=1,
                    node_id=cue.target))
        except Exception as exc:  # noqa: BLE001
            self._on_event(f"! {cue.track}: {exc}")

    def light_at(self, at_ms: int) -> tuple | None:
        """The stage light at a given time, without playing anything.

        Wanted by the export, which walks frames rather than firing
        cues, and by a preview that has been scrubbed to a new place.
        """
        if self.timeline is None:
            return None
        found = None
        for track in self.timeline.tracks:
            if track.kind != "light":
                continue
            for clip in track.clips:
                end = clip.t_offset_ms + (clip.duration_ms or 10 ** 9)
                if clip.t_offset_ms <= at_ms < end:
                    rgb = (clip.payload or {}).get("rgb") or []
                    if len(rgb) == 3:
                        found = (tuple(int(v) for v in rgb),
                                 float((clip.payload or {}).get("level", 0.35)))
        return found

    def _report(self) -> None:
        try:
            self._on_tick(self.state, self.position_ms, self.duration_ms)
        except Exception:  # noqa: BLE001 — a playhead is not worth a crash
            pass

    # ── dispatch ─────────────────────────────────────────────────

    def _fire(self, cue: Cue) -> None:
        payload = cue.clip.payload or {}
        try:
            if cue.kind == "animation":
                self.bus.publish(topics.DisplayCommand(
                    adapter=str(payload.get("adapter", "auto")),
                    asset_path=str(payload.get(
                        "asset", payload.get("asset_path", ""))),
                    duration_ms=int(cue.clip.duration_ms),
                    params=dict(payload.get("params", {})),
                    node_id=cue.target))
            elif cue.kind == "speech":
                self._speak(cue, payload, into_ms=0)
            elif cue.kind == "light":
                rgb = payload.get("rgb") or []
                if len(rgb) == 3:
                    self.light = tuple(int(v) for v in rgb)
                    self.light_level = float(payload.get("level", 0.35))
            elif cue.kind == "sound":
                self._sound(cue, payload, into_ms=0)
        except Exception as exc:  # noqa: BLE001
            self._on_event(f"! {cue.track}: {type(exc).__name__}: {exc}")


__all__ = ["Director", "Cue", "cues", "duration_of", "TICK_S",
           "IDLE", "PREROLL", "PLAYING", "PAUSED", "COMPLETE"]
