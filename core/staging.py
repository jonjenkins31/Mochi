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
    return timeline


def load(path: Any, project_root: pathlib.Path | None = None) -> Timeline:
    """Read a scene and resolve it against the characters it names."""
    path = pathlib.Path(path)
    root = pathlib.Path(project_root or pathlib.Path(__file__).resolve().parent.parent)
    return resolve(load_timeline(path), root)


def available(project_root: pathlib.Path | None = None) -> tuple:
    """(name, path) for every scene in assets/timelines/.

    Scenes live at the project level rather than in a character pack
    because a scene may have more than one character in it — that is the
    whole reason a track has a target.
    """
    root = pathlib.Path(project_root or pathlib.Path(__file__).resolve().parent.parent)
    return tuple((path.stem.replace("_", " "), path)
                 for path in sorted((root / "assets" / "timelines").glob("*.json")))


__all__ = ["StagingError", "load", "resolve", "available"]
