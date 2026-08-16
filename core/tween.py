"""Waypoints for procedural scenes — the motion half of a math command.

A robot program does not list every position it passes through. It
names the ones that matter and says how to get between them:

    L P[2] 500mm/sec CNT50

`MOVE` is that, for a math scene's parameters. A waypoint is a set of
tokens; a path is waypoints in order; the ease is the `FINE`/`CNT`
decision — stop dead on each one, or round the corner.

    [Keyframes start]
    P[1]: STATE[idle] GAZE[0,0]   TILT[0]
    P[2]: STATE[idle] GAZE[-0.85,0] TILT[-15]
    P[3]: STATE[alert] GAZE[0.85,0] TILT[10]
    [Keyframes end]

    [Main start]
    MOVE K[1] PATH[1,2,3] D[6.0] EASE[smooth]
    [Main end]

WHY THE SCENE TWEENS AND NOT THE CONDUCTOR. There is no topic that
updates a RUNNING clip — the display contract can start one and stop
one, nothing else. A conductor tweening by republishing would restart
the clip on every frame, which resets its clock and is visibly worse
than not tweening at all. So the whole path rides in the clip's params
and the scene walks it against its own `t`, at frame rate rather than
bus rate.

WHAT BLENDS AND WHAT SNAPS. Numbers, colours and pairs interpolate.
Anything else — `STATE[alert]`, `LAYERS[bezel,pupil]` — is a WORD, and
half of a word is nothing, so it changes at the midpoint. That rule is
why `MOVE` between two different states looks like a cut inside a move
rather than a smear.
"""

from __future__ import annotations

import re
from typing import Any

#: `FINE` stops on the point. `CNT` rounds the corner — the same choice
#: a motion statement makes, spelled the way this format spells things.
EASE = {
    "fine": lambda f: f,                                   # linear, hard stop
    "linear": lambda f: f,
    "smooth": lambda f: f * f * (3 - 2 * f),               # ease in and out
    "cnt": lambda f: f * f * (3 - 2 * f),
    "in": lambda f: f * f,
    "out": lambda f: 1 - (1 - f) * (1 - f),
}

_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]*)\]")


def parse_waypoints(lines: Any) -> dict[str, dict]:
    """`P[1]: STATE[idle] GAZE[0,0]` -> {"1": {"STATE": "idle", ...}}.

    Same shape as `[Resources]`, because a keyframe is a named thing
    referred to by number and there was no reason to invent a second
    way to write that down.
    """
    table: dict[str, dict] = {}
    for line in lines or ():
        key, _, rest = str(line).partition(":")
        key = key.strip()
        if not (key.startswith("P[") and key.endswith("]")):
            continue
        table[key[2:-1].strip()] = {
            name.upper(): value.strip()
            for name, value in _TOKEN.findall(rest)}
    return table


def _numeric(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _colour(text: str) -> tuple | None:
    text = str(text).strip()
    if text.startswith("#") and len(text) == 7:
        try:
            return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return None
    return None


def _pair(text: str) -> tuple | None:
    parts = str(text).split(",")
    if len(parts) != 2:
        return None
    a, b = _numeric(parts[0]), _numeric(parts[1])
    return (a, b) if a is not None and b is not None else None


def blend(a: Any, b: Any, f: float) -> Any:
    """One token, part way from `a` to `b`.

    Falls through in order of specificity and gives up into a snap,
    which is the honest answer for anything that is not on a line
    between two values.
    """
    if a == b or a is None:
        return b
    number_a, number_b = _numeric(a), _numeric(b)
    if number_a is not None and number_b is not None:
        return number_a + (number_b - number_a) * f
    colour_a, colour_b = _colour(a), _colour(b)
    if colour_a and colour_b:
        return "#%02X%02X%02X" % tuple(
            int(round(x + (y - x) * f)) for x, y in zip(colour_a, colour_b))
    pair_a, pair_b = _pair(a), _pair(b)
    if pair_a and pair_b:
        return "%.4f,%.4f" % tuple(
            x + (y - x) * f for x, y in zip(pair_a, pair_b))
    return a if f < 0.5 else b        # a word; half of one is nothing


class Path:
    """Waypoints in order, sampled by fraction of the whole move."""

    def __init__(self, stops: list, ease: str = "smooth",
                 loop: bool = False) -> None:
        self.stops = [dict(stop) for stop in stops if stop]
        self.curve = EASE.get(str(ease).lower().rstrip("0123456789"),
                              EASE["smooth"])
        self.loop = loop

    def __len__(self) -> int:
        return len(self.stops)

    def at(self, u: float) -> dict:
        """Params at `u` in 0..1 across the whole path.

        A path of one is a constant, which is what makes `MOVE` with a
        single waypoint a perfectly good way to just set something.
        """
        if not self.stops:
            return {}
        if len(self.stops) == 1:
            return dict(self.stops[0])
        u = (u % 1.0) if self.loop else max(0.0, min(1.0, u))
        span = len(self.stops) - 1
        scaled = u * span
        index = min(int(scaled), span - 1)
        f = self.curve(max(0.0, min(1.0, scaled - index)))
        here, then = self.stops[index], self.stops[index + 1]
        # The union of both ends: a token that only one waypoint
        # mentions still has to survive the move.
        out = {**here, **then}
        for key in out:
            out[key] = blend(here.get(key), then.get(key, here.get(key)), f)
        return out


def path_from(params: dict) -> Path | None:
    """Build a path out of whatever a clip was handed, or None.

    Scenes call this in `on_enter` and keep the result; it is the one
    piece both a math character and the conductor have to agree on.
    """
    stops = params.get("waypoints") or params.get("path")
    if not stops:
        return None
    if isinstance(stops, str):
        import json

        try:
            stops = json.loads(stops)
        except ValueError:
            return None
    if not isinstance(stops, list) or not stops:
        return None
    return Path(stops, str(params.get("ease", "smooth")),
                loop=str(params.get("pathloop", "")).lower()
                in ("1", "true", "yes"))


__all__ = ["EASE", "Path", "blend", "parse_waypoints", "path_from"]
