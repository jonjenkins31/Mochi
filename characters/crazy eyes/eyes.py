"""Crazy Eyes — one rigged eye, built twice.

Was a still image. It is a RIG now: a stack of rings and circles that
each turn at their own rate, and controls that aim the whole thing.
Nothing here is a picture.

ONE EYE CLASS, TWO EYES. `Eye` knows how to draw exactly one; the scene
holds two of them and hands each a centre. They are identical by
construction rather than by copy-paste, which is what makes "both eyes
blink together" free and "the left one lags" possible later.

THE STACK IS DATA, not code. Every ring below is a row in `LAYERS`:

    kind      disc | ring | ticks | cross | brackets | glow
    at        where, as a fraction of the socket radius
    width     how thick, same units
    value     how bright, 0..1
    rate      turns per second, SIGNED
    follow    how much of the gaze it takes — the parallax
    dilates   whether the pupil control resizes it

Retuning the look is editing that table. Adding a ring is adding a row.
The radii in it are MEASURED off the original artwork — its brightest
ring sits at 0.70 of the socket, its dark gap at 0.40, its core is a
donut peaking at 0.20 — so this reads as the same character rather than
a new one.

LAYERS ARE THE ANIMATION. Nothing is keyframed. The bezel turns one
way, the reticle the other, the iris faster than both, so the picture
never repeats and no clip had to be authored.

THE RIG IS THE PARALLAX. `gaze` aims the eye and the layers do NOT move
together — the pupil travels furthest, the iris less, the bezel barely,
the glow not at all. That disagreement is the entire reason a flat
stack of circles reads as a sphere turning to look at you.

THE RIG, top down. Each level owns its own transform, so a head tilt
carries the eyes and an eye roll does not move the head.

    head    PAN[x,y]  TILT[deg]  SCALE[n]  SPACING[n]
    eye     SIZE[n]  ROLL[deg]  LEFT[x,y]  RIGHT[x,y]  WINK[left]
            GAZE[x,y] / LOOK[word]  BLINK[0..1]  DILATE[n]  SPIN[n]
    layer   LAYERS[a,b,c]  TUNE[iris.rate=0.4;bezel.at=0.55]
    ink     COLOR[#51DAF8]  BRIGHTNESS[n]  BLOOM[n]  BG[r,g,b]
    time    SPD[n]  STATE[name]

`TUNE` is the escape hatch that keeps this list short: without it every
property of every layer would need its own token and the table above
would stop being editable data. `LAYERS` draws a SUBSET, which is how
the walkthrough can build the eye up one ring at a time.

All optional, all with a resting default, so `MATH K[1]` on its own is
a working pair of eyes.

BLACK IS NOT A COLOUR HERE. It is the pixels that are off — the eyes
are the whole picture and the background is whatever the display does
with zero.
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

#: Measured off the original artwork: two eyes 139px apart in a 480-wide
#: frame, each about 40px of socket. Fractions, so the rig survives any
#: canvas size.
SPACING = 139 / 480
RADIUS = 40 / 268

#: THE STACK. Outermost first is not required — `at` decides where it
#: lands — but reading it in radial order is how you check it against
#: the artwork.
LAYERS: tuple[dict, ...] = (
    # the glow. Fills between the rings, which is most of why the
    # original looks lit rather than drawn.
    {"name": "halo",    "kind": "glow", "at": 1.05, "value": 0.10,
     "rate": 0.0, "follow": 0.0, "falloff": 2.4},
    {"name": "bloom",   "kind": "glow", "at": 0.62, "value": 0.42,
     "rate": 0.0, "follow": 0.30, "falloff": 1.5},

    # bezel — the outer assembly. Brightest thing in the eye at 0.70.
    {"name": "rim",     "kind": "ring", "at": 0.90, "width": 0.05,
     "value": 0.38, "rate": 0.0, "follow": 0.10},
    {"name": "teeth",   "kind": "ticks", "at": 0.80, "width": 0.055,
     "value": 0.48, "rate": 0.055, "follow": 0.10, "count": 24, "duty": 0.40},
    {"name": "bezel",   "kind": "ring", "at": 0.70, "width": 0.085,
     "value": 1.00, "rate": 0.0, "follow": 0.10},

    # reticle — the overlay, turning the other way.
    {"name": "cross",   "kind": "cross", "at": 1.00, "width": 0.022,
     "value": 0.45, "rate": -0.031, "follow": 0.34, "gap": 0.34},
    {"name": "corners", "kind": "brackets", "at": 0.50, "width": 0.03,
     "value": 0.55, "rate": -0.031, "follow": 0.34},

    # iris — the fastest layer, and the one carrying the segments.
    {"name": "iris",    "kind": "ticks", "at": 0.60, "width": 0.07,
     "value": 0.55, "rate": 0.14, "follow": 0.55, "count": 12, "duty": 0.30},
    {"name": "limbus",  "kind": "ring", "at": 0.52, "width": 0.028,
     "value": 0.40, "rate": 0.0, "follow": 0.55},

    # pupil — a DONUT. The original's centre is darker than the ring
    # around it, which is what makes it an aperture and not a dot.
    {"name": "halo_in", "kind": "ring", "at": 0.30, "width": 0.035,
     "value": 0.62, "rate": 0.0, "follow": 0.95, "dilates": True},
    {"name": "iris_in", "kind": "ring", "at": 0.20, "width": 0.070,
     "value": 1.00, "rate": 0.0, "follow": 0.95, "dilates": True},
    {"name": "pupil",   "kind": "disc", "at": 0.13, "value": 0.14,
     "rate": 0.0, "follow": 0.95, "dilates": True},
)

#: Named looks. A preset is only token defaults, so everything in one
#: can also be written by hand on the MATH line.
STATES: dict[str, dict] = {
    "idle":       {},
    "alert":      {"dilate": 0.62, "spin": 2.4, "brightness": 1.25},
    "scan":       {"sweep": 1.0, "spin": 1.6},
    "look_left":  {"gaze": (-0.85, 0.0)},
    "look_right": {"gaze": (0.85, 0.0)},
    "look_up":    {"gaze": (0.0, -0.8)},
    "look_down":  {"gaze": (0.0, 0.75)},
    "squint":     {"blink": 0.45, "dilate": 0.8},
    "closed":     {"blink": 1.0},
    "cross":      {"converge": 1.0, "dilate": 1.15},
    "dizzy":      {"spin": 5.0, "wobble": 1.0, "dilate": 1.3},
}

#: `LOOK[left]` — words, so a script never has to know up is negative.
AIM = {"left": (-0.85, 0.0), "right": (0.85, 0.0), "up": (0.0, -0.8),
       "down": (0.0, 0.75), "center": (0.0, 0.0), "centre": (0.0, 0.0),
       "upleft": (-0.6, -0.55), "upright": (0.6, -0.55),
       "downleft": (-0.6, 0.5), "downright": (0.6, 0.5)}


def _blur(field: np.ndarray, radius: int) -> np.ndarray:
    """Separable box blur, twice — a cheap gaussian.

    Bloom is not decoration here: the original is a photographed glow,
    so light spills BETWEEN its rings, and a stack of clean annuli reads
    as a diagram of the eye rather than the eye. Measured against the
    artwork's radial profile, this is most of the remaining difference.
    """
    if radius < 1:
        return field
    out = field
    for _ in range(2):
        pad = np.pad(out, ((radius, radius), (radius, radius)), mode="edge")
        cumulative = np.cumsum(np.cumsum(pad, axis=0), axis=1)
        cumulative = np.pad(cumulative, ((1, 0), (1, 0)))
        size = 2 * radius + 1
        h, w = field.shape
        out = (cumulative[size:size + h, size:size + w]
               - cumulative[0:h, size:size + w]
               - cumulative[size:size + h, 0:w]
               + cumulative[0:h, 0:w]) / (size * size)
    return out


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


def _names(value: Any, fallback: tuple) -> tuple:
    """`LAYERS[bezel,pupil]` — draw only these. An empty value means
    every one, which is the difference between "all" and "none"."""
    if isinstance(value, str) and value.strip():
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part) for part in value)
    return tuple(fallback)


def _tune(value: Any, fallback: dict) -> dict:
    """`TUNE[iris.rate=0.4;bezel.value=0.3]` — reach one ring.

    The escape hatch that keeps the token list short. Without it, every
    property of every layer would need its own token, and the table
    would stop being editable data.
    """
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
        out.setdefault(layer.strip(), {})[field.strip()] = _number(
            raw, 0.0) if raw.strip().lstrip("-").replace(".", "", 1).isdigit(
            ) else raw.strip()
    return out


def _pair(value: Any, fallback: tuple) -> tuple:
    """`GAZE[0.6,-0.2]`, a word from AIM, or a 2-tuple."""
    if isinstance(value, str):
        word = value.strip().lower()
        if word in AIM:
            return AIM[word]
        parts = word.split(",")
        if len(parts) == 2:
            return (_number(parts[0], fallback[0]),
                    _number(parts[1], fallback[1]))
        return fallback
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (_number(value[0], fallback[0]), _number(value[1], fallback[1]))
    return fallback


class Eye:
    """ONE eye. The scene builds two and gives each a centre.

    Not an `Animation` subclass on purpose — the adapter picks the first
    one it finds, and this is a part, not a scene.
    """

    def __init__(self) -> None:
        # ── this eye's own transform, under the head's ──
        self.offset = (0.0, 0.0)   # fractions of socket radius
        self.roll = 0.0            # degrees, this eye alone
        self.scale = 1.0
        # ── the rig ──
        self.gaze = (0.0, 0.0)
        self.blink = 0.0
        self.dilate = 1.0
        self.spin = 1.0
        self.sweep = 0.0
        #: `layer.field = value`, applied over the shared LAYERS table.
        #: How a script reaches a single ring without this file growing
        #: a token per ring per property.
        self.overrides: dict[str, dict] = {}
        #: Which layers to draw at all. Empty means every one.
        self.only: tuple = ()

    def layer(self, spec: dict) -> dict:
        """One row, with this eye's overrides applied. The table stays
        shared and immutable; an eye only ever holds its differences."""
        patch = self.overrides.get(spec["name"])
        return {**spec, **patch} if patch else spec

    def draw(self, canvas: np.ndarray, cx: float, cy: float, radius: float,
             clock: float, seed: float = 0.0, extra_roll: float = 0.0) -> None:
        """Add this eye to the coverage buffer.

        Works on a LOCAL window: an eye covers a fifth of the frame and
        computing polar coordinates for the rest is four fifths of the
        work thrown away.
        """
        radius = radius * max(0.05, self.scale)
        cx += self.offset[0] * radius
        cy += self.offset[1] * radius
        pad = radius * 1.35
        x0 = max(0, int(cx - pad))
        x1 = min(canvas.shape[1], int(cx + pad) + 1)
        y0 = max(0, int(cy - pad))
        y1 = min(canvas.shape[0], int(cy + pad) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        view = canvas[y0:y1, x0:x1]
        xs = np.arange(x0, x1, dtype=np.float32) - cx + 0.5
        ys = np.arange(y0, y1, dtype=np.float32) - cy + 0.5
        dx = np.broadcast_to(xs[None, :], view.shape)
        dy = np.broadcast_to(ys[:, None], view.shape)

        # The eye's own roll turns its local frame, so every layer's
        # ticks, brackets and crosshair come with it — a roll that only
        # spun the reticle would be the overlay sliding off the eye.
        roll = self.roll + extra_roll
        if roll:
            turn = math.radians(roll)
            c, s_ = math.cos(turn), math.sin(turn)
            dx, dy = dx * c + dy * s_, -dx * s_ + dy * c

        aim_x = max(-1.0, min(1.0, self.gaze[0])) * radius * 0.30
        aim_y = max(-1.0, min(1.0, self.gaze[1])) * radius * 0.30
        breathe = 1 + 0.05 * math.sin(clock * 1.9 + seed)

        for spec in LAYERS:
            if self.only and spec["name"] not in self.only:
                continue
            layer = self.layer(spec)
            follow = layer.get("follow", 0.0)
            ox = dx - aim_x * follow + layer.get("dx", 0.0) * radius
            oy = dy - aim_y * follow + layer.get("dy", 0.0) * radius
            r = np.sqrt(ox * ox + oy * oy)
            size = (self.dilate * breathe) if layer.get("dilates") else 1.0
            at = radius * layer["at"] * size
            width = radius * layer.get("width", 0.05) * max(0.5, size)
            phase = clock * layer.get("rate", 0.0) * self.spin
            self._paint(view, layer, ox, oy, r, at, width, phase)

        if self.sweep:
            # A bar of light crossing the iris — `scan`. Its own clock,
            # so it need not divide into any layer's rate.
            band = ((clock * 0.6) % 1.0) * 2 - 1
            near = np.clip(1 - np.abs(dy / (radius * 0.55) - band) * 5, 0, 1)
            inside = np.clip((radius * 0.62 - np.sqrt(dx * dx + dy * dy))
                             * 0.5, 0, 1)
            np.maximum(view, near * inside * self.sweep * 0.9, out=view)

        if self.blink > 0.001:
            # A lid closes from BOTH edges toward the middle. A
            # shrinking disc reads as the eye retreating, not blinking.
            edge = radius * 1.25 * (1 - min(1.0, self.blink))
            view *= 1.0 - np.clip((np.abs(dy) - edge) * 2.0, 0, 1)

    @staticmethod
    def _paint(view, layer, ox, oy, r, at, width, phase) -> None:
        """One row of the stack. Every kind reduces to `maximum` against
        the buffer, so layers can never darken each other — only the lid
        does that, and it does it last."""
        kind = layer["kind"]
        value = layer.get("value", 1.0)
        if value <= 0.004:
            return
        soft = max(0.75, width * 0.6)

        if kind == "glow":
            np.maximum(view, np.clip(1.0 - r / max(1e-6, at), 0, 1)
                       ** layer.get("falloff", 2.0) * value, out=view)
        elif kind == "disc":
            np.maximum(view, np.clip(at - r + 0.5, 0, 1) * value, out=view)
        elif kind == "ring":
            np.maximum(view, np.clip((width - np.abs(r - at)) / soft, 0, 1)
                       * value, out=view)
        elif kind == "ticks":
            # A smooth ring turning looks like a ring. Teeth are what
            # make rotation visible at all.
            theta = np.arctan2(oy, ox) % TAU
            wrapped = (theta * layer.get("count", 12) / TAU
                       + phase * layer.get("count", 12)) % 1.0
            duty = layer.get("duty", 0.4)
            on = np.clip((duty - np.abs(wrapped - 0.5) * 2 + 0.5) * 4, 0, 1)
            band = np.clip((width - np.abs(r - at)) / soft, 0, 1)
            np.maximum(view, band * on * value, out=view)
        elif kind == "cross":
            turn = phase * TAU
            c, s = math.cos(turn), math.sin(turn)
            u, v = ox * c + oy * s, -ox * s + oy * c
            gap = at * layer.get("gap", 0.3)
            for along, across in ((u, v), (v, u)):
                bar = np.clip((width - np.abs(across)) / max(0.75, width), 0, 1)
                span = np.clip((at - np.abs(along)) / 2.0, 0, 1)
                hole = np.clip((np.abs(along) - gap) / 2.0, 0, 1)
                np.maximum(view, bar * span * hole * value, out=view)
        elif kind == "brackets":
            theta = (np.arctan2(oy, ox) - phase * TAU) % TAU
            quarter = (theta % (TAU / 4)) / (TAU / 4)
            arc = np.clip((0.34 - np.abs(quarter - 0.5)) * 8, 0, 1)
            band = np.clip((width - np.abs(r - at)) / max(0.75, width), 0, 1)
            np.maximum(view, band * arc * value, out=view)


class Eyes(Animation):
    """The scene: two `Eye`s, aimed together."""

    amplitude_param: float = 0.0

    def __init__(self, width: int, height: int) -> None:
        super().__init__(int(width), int(height))
        self.left, self.right = Eye(), Eye()
        self.state = "idle"
        # ── the head: the frame the eyes are mounted in ──
        self.pan = (0.0, 0.0)      # fractions of the frame, not pixels
        self.tilt = 0.0            # degrees; turns the whole face
        self.scale = 1.0
        self.spacing = 1.0         # eye separation multiplier
        self.speed = 1.0
        self.wobble = 0.0
        self.converge = 0.0
        self.brightness = 1.0
        #: How much light spills between the rings. 0 is a clean
        #: diagram; 0.30 is where the artwork's own radial profile
        #: puts it — fitted, not guessed.
        self.bloom = 0.30
        self.color = (81, 218, 248)
        #: Pure black: these are pixels that are OFF, not a colour
        #: choice. The eyes are the whole picture.
        self.background = (0, 0, 0)

    @property
    def eyes(self) -> tuple:
        return (self.left, self.right)

    def on_enter(self, **kwargs: Any) -> None:
        """Preset first, explicit tokens over it — so `STATE[alert]
        GAZE[-0.5,0]` is an alert eye looking left."""
        params = {str(k).lower(): v for k, v in kwargs.items()}

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
        self.spacing = _number(pick("spacing"), preset.get("spacing", 1.0))
        self.wobble = _number(pick("wobble"), preset.get("wobble", 0.0))
        self.converge = _number(pick("converge"), preset.get("converge", 0.0))
        self.brightness = _number(pick("brightness"),
                                  preset.get("brightness", 1.0))
        self.bloom = _number(pick("bloom"), preset.get("bloom", 0.30))
        self.color = _rgb(pick("color", "fg"), self.color)
        self.background = _rgb(pick("background", "bg"), self.background)

        # Both eyes get the same rig. One object each, so a future
        # script can desynchronise them without this changing.
        overrides = _tune(pick("tune"), preset.get("tune", {}))
        only = _names(pick("layers"), preset.get("layers", ()))
        for eye in self.eyes:
            eye.gaze = _pair(pick("gaze", "look"),
                             preset.get("gaze", (0.0, 0.0)))
            eye.blink = _number(pick("blink"), preset.get("blink", 0.0))
            eye.dilate = _number(pick("dilate"), preset.get("dilate", 1.0))
            eye.spin = _number(pick("spin"), preset.get("spin", 1.0))
            eye.sweep = _number(pick("sweep"), preset.get("sweep", 0.0))
            eye.roll = _number(pick("roll"), preset.get("roll", 0.0))
            eye.scale = _number(pick("size"), preset.get("size", 1.0))
            eye.offset = (0.0, 0.0)
            eye.overrides = overrides
            eye.only = only

        # Asymmetry LAST, so it overrides what both eyes just took.
        # `WINK[left]` is the whole reason an Eye is an object rather
        # than a set of numbers on the scene.
        wink = str(pick("wink", default="")).strip().lower()
        if wink in ("left", "right"):
            (self.left if wink == "left" else self.right).blink = 1.0
        for side, eye in (("left", self.left), ("right", self.right)):
            eye.offset = _pair(pick(side), eye.offset)

    def on_event(self, event: str, **kwargs: Any) -> None:
        """Re-aim mid-clip without restarting it — the point of a rig.
        `on_enter` would reset the clock and jump the animation."""
        if event in STATES:
            self.on_enter(state=event, **kwargs)
        elif event in AIM:
            for eye in self.eyes:
                eye.gaze = AIM[event]
        elif kwargs:
            self.on_enter(state=self.state, **kwargs)

    def render_into(self, t: float, frame_rgb: np.ndarray) -> None:
        height, width = frame_rgb.shape[0], frame_rgb.shape[1]
        frame_rgb[:, :] = self.background
        clock = t * self.speed

        radius = max(3.0, min(width * SPACING * 0.62,
                              height * RADIUS) * max(0.05, self.scale))
        gap = min(width * SPACING, width * 0.5 - radius * 1.2) * self.spacing
        # The head's own origin, so PAN moves the face rather than
        # cropping it.
        hx = width / 2 + self.pan[0] * width * 0.5
        hy = height / 2 + self.pan[1] * height * 0.5
        turn = math.radians(self.tilt)
        cos_t, sin_t = math.cos(turn), math.sin(turn)
        canvas = np.zeros((height, width), dtype=np.float32)

        for index, (side, eye) in enumerate(zip((-1, 1), self.eyes)):
            # Converge pulls the eyes toward each other; wobble drifts
            # the socket itself, which no amount of gaze can do.
            drift_x = self.wobble * radius * 0.10 * math.sin(clock * 2.3 + side)
            drift_y = self.wobble * radius * 0.08 * math.sin(clock * 1.7)
            # Where this eye sits IN THE HEAD, before the head turns.
            ex = side * gap / 2 - side * self.converge * radius * 0.30 + drift_x
            ey = drift_y
            # TILT rotates the mounting, not just the eyeballs: the pair
            # swings about the head's centre AND each eye rolls with it,
            # which is a head tilting rather than two eyes spinning.
            eye.draw(canvas, hx + ex * cos_t - ey * sin_t,
                     hy + ex * sin_t + ey * cos_t, radius, clock,
                     seed=index, extra_roll=self.tilt)

        np.clip(canvas, 0.0, 1.0, out=canvas)
        if self.bloom > 0.001:
            canvas = np.clip(
                canvas + _blur(canvas, max(1, int(radius * 0.18)))
                * self.bloom * 2.6, 0.0, 1.0)
        base = np.asarray(self.background, dtype=np.float32)
        ink = np.clip(np.asarray(self.color, dtype=np.float32)
                      * self.brightness, 0, 255)
        frame_rgb[:, :] = (base + (ink - base) * canvas[:, :, None]
                           ).astype(np.uint8)
