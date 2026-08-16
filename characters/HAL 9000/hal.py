"""HAL 9000 — one lens, drawn from maths.

Was a photograph. It is a rig now, and it is the second math character
after Crazy Eyes, which makes it the test of whether that pattern
generalises. Two things it does that the eyes do not:

    ONE EYE, NOT A PAIR.  There is no spacing, no convergence, no
    winking. The whole rig points at the head transform instead, and
    the layer stack got simpler by losing an entire concept.

    COLOUR PER LAYER.     Crazy Eyes is monochrome — one ink, and
    every ring is a brightness of it. HAL is not: a deep red field
    with a hot yellow-white core is the character, and rendering it in
    one colour makes a red circle, not HAL. So each layer carries its
    own RGB and they composite.

That second one is the interesting result. A math character is not
"rings in a colour" — it is a stack with a colour each, and the eyes
were the special case all along.

THE STACK, outside in:

    plate     the housing it is set into, barely lit
    bezel     the metal rim
    well      the dark glass the lens sits in
    bloom     the red spill onto everything
    iris      the red annulus — the bit everyone remembers
    core      the hot centre, yellow into white
    catch     one specular highlight, off to one side

CONTROLS, as mscript tokens on the MATH command:

    STATE[alarmed]     a named preset
    SIZE[1.4]          the lens itself, and what the demo leans on
    PAN[x,y] TILT[deg] SCALE[n]     the housing
    COLOR[#FF2200]     the field
    CORE[#FFE9A8]      the hot centre
    GLOW[1.6]          how far the red spills
    PULSE[0.4] RATE[2] breathing depth and speed
    SCAN[1]            a readout line crossing the lens
    DIM[0.3]           overall brightness — 0 is powered down
    LAYERS[iris,core]  draw a subset
    TUNE[iris.at=0.5]  reach one layer
    SPD[n]             time itself

All optional and all with a resting default, so `MATH K[1]` alone is
HAL sitting there watching you.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    from plugin_core.mochi_animations import Animation
except ImportError:  # rendered outside the node — dev/tools/make_cards.py
    class Animation:  # noqa: D101
        def __init__(self, w: int, h: int) -> None:
            self.w, self.h = w, h

        def on_enter(self, **kwargs: Any) -> None: ...

        def on_event(self, event: str, **kwargs: Any) -> None: ...

        def set_size(self, w: int, h: int) -> None:
            self.w, self.h = w, h

TAU = math.pi * 2

#: `radius` throughout this file means the RED LENS, not the housing —
#: measured off the reference photo, where the glow is r=15, the dark
#: well runs to r=50 and the bright plate sits at r=60-90. So the well
#: is 3.3x the lens and the plate is 5x, and every `at` below is a
#: multiple of the lens rather than of the panel.
#:
#: Getting this backwards is the commonest way to draw HAL wrong: a red
#: disc filling the housing instead of a small hot eye in a lot of
#: black.
LENS = 0.078

#: The stack. `tint` names which colour control a layer follows, so
#: `COLOR` moves the field and `CORE` moves the centre without either
#: token needing to know which rows it touches.
LAYERS: tuple[dict, ...] = (
    {"name": "plate",  "kind": "glow", "at": 8.0, "value": 0.05,
     "tint": "plate", "falloff": 1.3},
    {"name": "bezel",  "kind": "ring", "at": 5.0, "width": 1.5,
     "value": 0.34, "tint": "plate"},
    {"name": "rim",    "kind": "ring", "at": 3.6, "width": 0.28,
     "value": 0.60, "tint": "plate"},
    {"name": "well",   "kind": "disc", "at": 3.3, "value": 0.055,
     "tint": "well"},
    {"name": "bloom",  "kind": "glow", "at": 3.1, "value": 0.30,
     "tint": "field", "falloff": 2.3, "glows": True},
    {"name": "iris",   "kind": "disc", "at": 1.00, "value": 0.95,
     "tint": "field", "pulses": True},
    {"name": "ring",   "kind": "ring", "at": 1.05, "width": 0.30,
     "value": 1.00, "tint": "field", "pulses": True},
    {"name": "core",   "kind": "disc", "at": 0.42, "value": 1.00,
     "tint": "core", "pulses": True},
    {"name": "catch",  "kind": "disc", "at": 0.18, "value": 0.80,
     "tint": "catch", "dx": -0.34, "dy": -0.38},
)

#: Named looks. HAL's range is narrow on purpose — he does not emote,
#: he changes intensity, which is most of why he is frightening.
STATES: dict[str, dict] = {
    "idle":     {},
    "watching": {"pulse": 0.10, "rate": 0.5, "glow": 1.15, "size": 1.05},
    "thinking": {"pulse": 0.34, "rate": 2.4, "glow": 1.25, "scan": 0.55},
    "reading":  {"scan": 1.0, "pulse": 0.14, "rate": 1.4},
    "alarmed":  {"pulse": 0.55, "rate": 5.5, "glow": 1.9, "size": 1.22,
                 "color": "#FF3018"},
    "cold":     {"pulse": 0.04, "rate": 0.3, "glow": 0.75, "size": 0.92,
                 "color": "#C81400"},
    "dying":    {"pulse": 0.30, "rate": 0.7, "glow": 0.55, "size": 0.72,
                 "dim": 0.45, "color": "#B41000"},
    "off":      {"dim": 0.0},
}


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _rgb(value: Any, fallback: tuple) -> tuple:
    if isinstance(value, str) and "," in value:
        value = [p.strip() for p in value.split(",")]
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(max(0, min(255, int(float(c)))) for c in value)
        except (TypeError, ValueError):
            return fallback
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return fallback
    return fallback


def _pair(value: Any, fallback: tuple) -> tuple:
    if isinstance(value, str):
        parts = value.split(",")
        if len(parts) == 2:
            return (_number(parts[0], fallback[0]),
                    _number(parts[1], fallback[1]))
        return fallback
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (_number(value[0], fallback[0]), _number(value[1], fallback[1]))
    return fallback


def _names(value: Any, fallback: tuple) -> tuple:
    if isinstance(value, str) and value.strip():
        return tuple(p.strip() for p in value.split(",") if p.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(p) for p in value)
    return tuple(fallback)


def _tune(value: Any, fallback: dict) -> dict:
    """`TUNE[iris.at=0.5;core.value=0.7]` — reach one layer."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return dict(fallback)
    out: dict[str, dict] = {}
    for clause in value.replace(",", ";").split(";"):
        target, _, raw = clause.partition("=")
        layer, _, field = target.strip().partition(".")
        if not (layer and field and raw):
            continue
        number = _number(raw, None) if raw.strip().lstrip("-").replace(
            ".", "", 1).isdigit() else None
        out.setdefault(layer.strip(), {})[field.strip()] = (
            number if number is not None else raw.strip())
    return out


def _blur(field: np.ndarray, radius: int) -> np.ndarray:
    """Separable box blur, twice. HAL is a light source in a dark room;
    without spill he is a sticker of a red circle."""
    if radius < 1:
        return field
    out = field
    for _ in range(2):
        pad = np.pad(out, ((radius, radius), (radius, radius)), mode="edge")
        total = np.cumsum(np.cumsum(pad, axis=0), axis=1)
        total = np.pad(total, ((1, 0), (1, 0)))
        size = 2 * radius + 1
        h, w = field.shape
        out = (total[size:size + h, size:size + w]
               - total[0:h, size:size + w]
               - total[size:size + h, 0:w]
               + total[0:h, 0:w]) / (size * size)
    return out


def _path_from(params: dict) -> Any:
    """The app's waypoint interpolator, when the app is running it. A
    pack is content and does not depend on the application — and
    waypoints only ever arrive from the conductor, so nothing is lost
    when this fails."""
    try:
        from core.tween import path_from
    except ImportError:
        return None
    return path_from(params)


class Lens:
    """The eye. One of them, which is the whole difference from a pair.

    Not an `Animation` subclass: the adapter takes the first one it
    finds and this is a part, not a scene.
    """

    def __init__(self) -> None:
        self.scale = 1.0
        self.pulse = 0.16
        self.rate = 1.1
        self.glow = 1.0
        self.scan = 0.0
        self.overrides: dict[str, dict] = {}
        self.only: tuple = ()

    def layer(self, spec: dict) -> dict:
        patch = self.overrides.get(spec["name"])
        return {**spec, **patch} if patch else spec

    def draw(self, rgb: np.ndarray, cx: float, cy: float, radius: float,
             clock: float, tints: dict) -> None:
        """Composite the stack into an RGB float buffer.

        Colour per layer is the reason this writes RGB rather than a
        coverage mask: a red field with a yellow core cannot be one ink
        at two brightnesses, and pretending otherwise is how HAL comes
        out looking like a stop light.
        """
        radius = radius * max(0.02, self.scale)
        reach = radius * 9.0
        x0 = max(0, int(cx - reach)); x1 = min(rgb.shape[1], int(cx + reach) + 1)
        y0 = max(0, int(cy - reach)); y1 = min(rgb.shape[0], int(cy + reach) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        view = rgb[y0:y1, x0:x1]
        xs = np.arange(x0, x1, dtype=np.float32) - cx + 0.5
        ys = np.arange(y0, y1, dtype=np.float32) - cy + 0.5
        dx = np.broadcast_to(xs[None, :], view.shape[:2])
        dy = np.broadcast_to(ys[:, None], view.shape[:2])

        # HAL breathes. It is the only thing he does when nothing is
        # happening, and it is what makes him look switched on rather
        # than painted on.
        breath = 1 + self.pulse * math.sin(clock * self.rate * TAU * 0.5)

        for spec in LAYERS:
            if self.only and spec["name"] not in self.only:
                continue
            layer = self.layer(spec)
            ox = dx - layer.get("dx", 0.0) * radius
            oy = dy - layer.get("dy", 0.0) * radius
            r = np.sqrt(ox * ox + oy * oy)
            at = radius * layer["at"]
            if layer.get("pulses"):
                at *= breath
            if layer.get("glows"):
                at *= self.glow
            coverage = self._coverage(layer, r, at, radius)
            if coverage is None:
                continue
            colour = np.asarray(tints.get(layer.get("tint", "field"),
                                          (255, 255, 255)), dtype=np.float32)
            # Additive, because every one of these IS light. Clipping
            # happens once at the end so a bright core over a bright
            # field goes white rather than wrapping.
            view += coverage[:, :, None] * colour * layer.get("value", 1.0)

        if self.scan:
            # A readout line crossing the lens. Its own clock, so it
            # need not divide into the breathing rate.
            band = ((clock * 0.45) % 1.0) * 2 - 1
            near = np.clip(1 - np.abs(dy / (radius * 3.2) - band) * 6, 0, 1)
            inside = np.clip((radius * 3.1 - np.sqrt(dx * dx + dy * dy))
                             * 0.35, 0, 1)
            view += (near * inside * self.scan * 90)[:, :, None] * np.asarray(
                tints.get("core", (255, 255, 255)), dtype=np.float32) / 255

    @staticmethod
    def _coverage(layer: dict, r, at: float, radius: float):
        kind = layer["kind"]
        if kind == "glow":
            return np.clip(1.0 - r / max(1e-6, at), 0, 1) ** layer.get(
                "falloff", 2.0)
        if kind == "disc":
            return np.clip(at - r + 0.6, 0, 1)
        if kind == "ring":
            width = radius * layer.get("width", 0.05)
            return np.clip((width - np.abs(r - at)) / max(0.75, width * 0.6),
                           0, 1)
        return None


class Hal(Animation):
    """The scene: one lens in a housing."""

    amplitude_param: float = 0.0

    def __init__(self, width: int, height: int) -> None:
        super().__init__(int(width), int(height))
        self.lens = Lens()
        self.state = "idle"
        self._path = None
        self._move_s = 1.0
        # the housing
        self.pan = (0.0, 0.0)
        self.tilt = 0.0
        self.scale = 1.0
        self.speed = 1.0
        self.dim = 1.0
        self.bloom = 0.55
        self.background = (0, 0, 0)
        #: Named so a token can move one without naming the layers it
        #: applies to. `field` is the lens, `core` the hot centre.
        self.tints = {
            "field": (255, 26, 8),
            "core": (255, 231, 168),
            "catch": (255, 255, 255),
            "well": (14, 8, 8),
            "plate": (128, 122, 120),
        }

    def on_enter(self, **kwargs: Any) -> None:
        params = {str(k).lower(): v for k, v in kwargs.items()}
        if "waypoints" in params or "path" in params:
            self._path = _path_from(params)
            self._move_s = _number(params.get("duration"), 1.0)

        def pick(*names, default=None):
            for name in names:
                if params.get(name) not in (None, ""):
                    return params[name]
            return default

        state = str(pick("state", default="idle")).lower()
        self.state = state if state in STATES else "idle"
        preset = STATES[self.state]

        self.speed = _number(pick("speed", "spd"), 1.0)
        self.pan = _pair(pick("pan"), preset.get("pan", (0.0, 0.0)))
        self.tilt = _number(pick("tilt"), preset.get("tilt", 0.0))
        self.scale = _number(pick("scale"), preset.get("scale", 1.0))
        self.dim = _number(pick("dim"), preset.get("dim", 1.0))
        self.bloom = _number(pick("bloom"), preset.get("bloom", 0.55))
        self.background = _rgb(pick("background", "bg"), self.background)
        for name, token in (("field", "color"), ("core", "core"),
                            ("catch", "catch"), ("plate", "plate")):
            self.tints[name] = _rgb(pick(token), self.tints[name])

        lens = self.lens
        lens.scale = _number(pick("size"), preset.get("size", 1.0))
        lens.pulse = _number(pick("pulse"), preset.get("pulse", 0.16))
        lens.rate = _number(pick("rate"), preset.get("rate", 1.1))
        lens.glow = _number(pick("glow"), preset.get("glow", 1.0))
        lens.scan = _number(pick("scan"), preset.get("scan", 0.0))
        lens.overrides = _tune(pick("tune"), preset.get("tune", {}))
        lens.only = _names(pick("layers"), preset.get("layers", ()))

    def on_event(self, event: str, **kwargs: Any) -> None:
        if event in STATES:
            self.on_enter(state=event, **kwargs)
        elif kwargs:
            self.on_enter(state=self.state, **kwargs)

    def render_into(self, t: float, frame_rgb: np.ndarray) -> None:
        if self._path is not None:
            self.on_enter(**self._path.at(t / max(1e-6, self._move_s)))
        height, width = frame_rgb.shape[0], frame_rgb.shape[1]
        clock = t * self.speed

        radius = max(1.5, min(width, height) * LENS * 0.5
                     * max(0.02, self.scale))
        turn = math.radians(self.tilt)
        hx = width / 2 + self.pan[0] * width * 0.5
        hy = height / 2 + self.pan[1] * height * 0.5

        rgb = np.zeros((height, width, 3), dtype=np.float32)
        rgb[:, :] = self.background
        # Tilt is a housing rotation, and a single round lens does not
        # show one — so it moves the lens on an arc instead, which is
        # what a panel turning actually looks like.
        offset = radius * 0.35 * math.sin(turn)
        self.lens.draw(rgb, hx + offset, hy - radius * 0.12 * (1 - math.cos(turn)),
                       radius, clock, self.tints)

        if self.bloom > 0.001:
            glow = _blur(rgb.mean(axis=2), max(1, int(radius * 1.4)))
            rgb += glow[:, :, None] * self.bloom * 0.9
        rgb *= max(0.0, self.dim)
        np.clip(rgb, 0, 255, out=rgb)
        frame_rgb[:, :] = rgb.astype(np.uint8)
