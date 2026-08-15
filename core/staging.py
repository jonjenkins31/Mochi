"""Timelines that know about characters.

A timeline is tracks on one clock — the shape that expresses "look
around WHILE you talk", which a program counter cannot. JaegerOS owns
the schema and the scheduler and deliberately knows nothing about
character packs: its animation clips carry an asset path.

That is the gap this closes. An author wants to write

    {"character": "bitmap_man", "expression": "look_up"}

and not the path to a bitmap JSON three directories down. Resolving one
into the other needs the pack, so it happens HERE, at load, and the
runner still receives plain asset paths. JaegerOS stays generic; Mochi
knows what a face is.

WHY LOAD-TIME AND NOT DISPATCH-TIME. A missing expression should fail
when you open the scene, naming the clip, not silently skip a beat
three seconds into a performance in front of someone.

WHAT A TRACK'S TARGET IS FOR. `kind` says what a clip means; `target`
says who does it. One character does not need it. Two do — and so does
a body with three servos, or a rig with two displays. It is the
difference between a solo and a scene.
"""

from __future__ import annotations

import pathlib
from typing import Any

from jaeger_os.timeline import Timeline, load_timeline

from modules import jaeger_animation as animation


class StagingError(RuntimeError):
    """A timeline names something the character cannot do."""


def _asset_for(character: Any, expression: str) -> str:
    """The asset a character shows for one expression, project-relative.

    Reuses the pack's own declaration rather than guessing a path, so a
    character that stores its faces anywhere still resolves.
    """
    if expression not in character.expressions:
        raise StagingError(
            f"{character.name}: no expression {expression!r}; "
            f"has {sorted(character.expressions)}")
    spec = character.expressions[expression]
    asset = spec.get("asset") or spec.get("clips")
    if isinstance(asset, dict):          # clip_set: primary/alternate
        asset = asset.get("primary") or next(iter(asset.values()), "")
    if not asset:
        asset = character.render.get("asset", "")
    root = pathlib.Path(character.root)
    return str((root / str(asset)).resolve())


def resolve(timeline: Timeline, project_root: pathlib.Path) -> Timeline:
    """Turn every character/expression clip into an asset path.

    Mutates and returns the timeline. Clips that already name an asset
    are untouched, so a scene may mix hand-written paths with character
    expressions — which is what happens when someone drops one video in
    among a pack's faces.
    """
    cache: dict[str, Any] = {}
    for track in timeline.tracks:
        for clip in track.clips:
            payload = clip.payload or {}
            name = str(payload.get("character") or track.target or "").strip()
            expression = str(payload.get("expression") or "").strip()
            if not expression:
                continue
            if not name:
                raise StagingError(
                    f"clip {clip.label or expression!r} names an expression "
                    f"but no character, and its track has no target")
            if name not in cache:
                cache[name] = animation.load(name)
            payload["asset"] = _asset_for(cache[name], expression)
            payload.setdefault("adapter", "auto")
            clip.payload = payload
    _resolve_voices(timeline, cache)
    return timeline


def _resolve_voices(timeline: Timeline, cache: dict) -> None:
    """Give every speech clip the target character's own voice.

    A track's `target` is a CHARACTER id; a synthesiser wants a VOICE
    id, and only the pack knows which one. Same reason expressions
    resolve here: JaegerOS schedules, Mochi knows what a character is.

    A clip that names its own voice keeps it — that is how a scene makes
    a character audibly slip out of its own register, which is a
    performance decision and not a lookup.
    """
    import yaml

    for track in timeline.tracks:
        if track.kind != "speech" or not track.target:
            continue
        name = track.target
        if name not in cache:
            try:
                cache[name] = animation.load(name)
            except Exception:  # noqa: BLE001 — a light track targets a lamp
                continue
        try:
            sheet = yaml.safe_load(
                (pathlib.Path(cache[name].root) / "character.yaml")
                .read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        voice = str((sheet.get("identity") or {}).get("voice_id", "")).strip()
        if not voice:
            continue
        for clip in track.clips:
            payload = clip.payload or {}
            payload.setdefault("voice", voice)
            clip.payload = payload


def load(path: Any, project_root: pathlib.Path | None = None) -> Timeline:
    """Read a scene — written as a listing or as JSON — and resolve it.

    Both forms are scenes and a caller should not have to know which it
    picked from a list. `.mscript` is the authoring form and compiles;
    `.json` is the compiled form and loads. Handing an mscript to the
    JSON decoder is what produced `Expected 'object', got 'array'` the
    moment shared scenes started being offered.
    """
    from core import scenes as scene_lib

    path = pathlib.Path(path)
    root = pathlib.Path(project_root or pathlib.Path(__file__).resolve().parent.parent)
    if path.suffix == ".mscript":
        timeline = scene_lib.compile_timeline(path)
        if timeline is None:
            raise StagingError(f"{path.name} has no [Track_*] sections")
        return resolve(timeline, root)
    return resolve(load_timeline(path), root)


def available(character: Any = None,
              project_root: pathlib.Path | None = None) -> tuple:
    """(name, path) for the scenes a character owns, plus shared ones.

    A scene lives WITH its character, in `characters/<id>/scenes/`,
    beside the `mscripts/` it performs. It is not an asset — it
    references assets the way a score references instruments — and it is
    not project-level, because it names one character's expressions and
    will not play without that pack.

    The exception is real and has a home: `scenes/` at the project root
    is for a scene with MORE THAN ONE character in it. A two-hander is
    owned by neither of them, which is the whole reason a track carries
    a target. That directory does not exist yet and is not created
    speculatively — the first two-hander makes it.
    """
    root = pathlib.Path(project_root or pathlib.Path(__file__).resolve().parent.parent)
    found = []
    if character is not None:
        own = pathlib.Path(getattr(character, "root", "") or "") / "scenes"
        for pattern in ("*.json", "*.mscript"):
            found += [(p.stem.replace("_", " "), p) for p in sorted(own.glob(pattern))]
    shared = root / "scenes"
    for pattern in ("*.json", "*.mscript"):
        found += [(f"{p.stem.replace('_', ' ')}  (shared)", p)
                  for p in sorted(shared.glob(pattern))]
    return tuple(found)


__all__ = ["StagingError", "Conductor", "load", "resolve", "available"]


class Conductor:
    """Play a timeline whose tracks may hold CUES as well as events.

    This is the join between the two shapes, and the answer to "does a
    timeline run mscripts?" — it does, one runner per script track, all
    started against the same clock:

        track: eyes    ─ events ──┐
        track: voice   ─ events ──┼─ JaegerOS TimelineRunner (one clock)
        track: light   ─ events ──┘
        track: gesture ─ cue ─────── a SceneRunner, started at its offset
        track: idle    ─ cue ─────── another, concurrently

    So a track is the channel, a cue is a channel's program, and
    concurrency comes from having several tracks — not from making one
    sequencer multi-threaded, which is how you get a program counter
    that no longer reads like one.

    WHY THE SCHEDULER DOES NOT DO THIS ITSELF. JaegerOS owns the clock
    and the wire format; the sequencer lives in the app. Teaching the
    scheduler to run mscripts would make the timeline format depend on
    one particular sequencer, and the whole point of a track kind is
    that a consumer it has never heard of can own it.

    WHAT IT STILL CANNOT DO. A cue that LISTENs stops for a person, and
    a wall clock does not stop with it — the other tracks keep going and
    sync is lost after. That is the honest limit of putting a reactive
    thing on a fixed clock, and choosing per cue (hold the transport, or
    let it drift) is the next decision, not a thing to paper over.
    """

    def __init__(self, app: Any, character: Any) -> None:
        self.app = app
        self.character = character
        self._runners: list[Any] = []
        self._timers: list[Any] = []
        self._timeline: Any = None

    @property
    def running(self) -> bool:
        return bool(self._timeline and not self._timeline.finished)

    def perform(self, path: Any, target: str = "",
                on_event: Any = None) -> bool:
        """Play ONE mscript as a whole show: channels and program together.

        This is the animatronic shape. A show file is not a sequence OR
        a timeline — it is both at once, because a figure moves, speaks
        and reacts on the same beat:

            [Track_*]   channels on the clock. Move and speak together,
                        each on its own line, timed absolutely.
            [Main]      the show-control program. Can branch, can loop,
                        and can STOP for a person — the part a clock
                        cannot express.

        Both start from the same t=0 and run concurrently, so a figure
        can be mid-gesture when someone answers it.

        Returns False if the file has neither, which is not an error —
        an empty script is a script.
        """
        from core import scenes as scene_lib

        path = pathlib.Path(path)
        self.stop()
        started = False

        timeline = scene_lib.compile_timeline(path, target=target)
        if timeline is not None:
            from jaeger_os.timeline import TimelineRunner

            resolve(timeline, pathlib.Path(__file__).resolve().parent.parent)
            self._timeline = TimelineRunner(self.app.bus, timeline)
            self._timeline.start()
            started = True

        program = scene_lib.load(path)
        if program.steps:
            runner = scene_lib.SceneRunner(
                self.app, self.character, on_event=on_event)
            self._runners.append(runner)
            runner.start(program)
            started = True
        return started

    def start(self, timeline: Timeline,
              on_event: Any = None) -> None:
        """Start every track. Events go to the scheduler, cues to their
        own runner, all measured from the same t=0."""
        import threading

        from jaeger_os.timeline import TRACK_SCRIPT, TimelineRunner

        from core import scenes as scene_lib

        self.stop()
        events = Timeline(
            name=timeline.name, description=timeline.description,
            duration_ms=timeline.duration_ms, loop=timeline.loop,
            tracks=[t for t in timeline.tracks if t.kind != TRACK_SCRIPT])
        self._timeline = TimelineRunner(self.app.bus, events)
        self._timeline.start()

        for track in timeline.tracks:
            if track.kind != TRACK_SCRIPT:
                continue
            for clip in track.clips:
                path = str((clip.payload or {}).get("script", "")).strip()
                if not path:
                    continue
                runner = scene_lib.SceneRunner(
                    self.app, self.character, on_event=on_event)
                self._runners.append(runner)
                timer = threading.Timer(
                    max(0.0, clip.t_offset_ms / 1000.0),
                    self._fire, args=(runner, path))
                timer.daemon = True
                self._timers.append(timer)
                timer.start()

    def _fire(self, runner: Any, path: str) -> None:
        from core import scenes as scene_lib

        try:
            runner.start(scene_lib.load(path))
        except Exception:  # noqa: BLE001 — one bad cue, not a dead scene
            pass

    def wait(self, timeout: float | None = None) -> bool:
        return bool(self._timeline and self._timeline.wait(timeout=timeout))

    def stop(self) -> None:
        for timer in self._timers:
            timer.cancel()
        self._timers = []
        for runner in self._runners:
            runner.stop()
        self._runners = []
        if self._timeline is not None:
            self._timeline.stop()
            self._timeline = None
