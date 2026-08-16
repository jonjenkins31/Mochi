"""EVE — a lit visor: two rigged eyes and a mouth made of light.

Fourth math character, and the first with a MOUTH. That is the whole
reason it exists: Orbs, HAL and Halo all say things without anything
moving that could be called speech, and a face that talks needs a part
that talks.

THE STACK, as asked for:

    panel     the dark glass the whole face sits in
    halo      a LARGER circle behind everything, a glowing gradient
    texture   a scanline layer over the glass, so it reads as a screen
              and not as shapes floating in a void
    eye x2    a main circle with its own inner gradient
    mouth     a bar of light segments — the new rig

TWO RIGS, NOT ONE.

    The EYES do what EVE's eyes do, which is almost entirely TILT.
    Angled inward is a glare, angled outward is worry, level is calm,
    and that one number carries more of her range than colour or size
    ever could. Plus gaze, blink, squint, size and spacing.

    The MOUTH is a row of segments whose heights follow the voice. It
    is not a shape that opens and closes on a timer — when the speaker
    is running it is reading `amplitude_param`, the same live signal
    Halo's ring reads, so the mouth moves because sound is happening.

    Shapes underneath it: line, smile, frown, o, wave. A shape sets the
    RESTING profile and the level modulates it, so `smile` while
    speaking is a smile that talks rather than a smile that stops.

CONTROLS:

    STATE[curious]   idle happy sad angry curious scanning speaking sleeping
    LOOK[left] GAZE[x,y] BLINK[0..1] SQUINT[0..1]
    TILT[deg]        eye angle — the one that matters
    SIZE[n] SPACING[n] EYECOLOR[#8CE8FF]
    MOUTH[smile]     line smile frown o wave
    OPEN[0.6]        resting mouth height
    LEVEL[0.8]       force the voice level, for scripting in silence
    SEGS[13] MOUTHCOLOR[#FFFFFF]
    GLOW[n] TEXTURE[n] COLOR[#0A1A24] PAN[x,y] SCALE[n] DIM[n] SPD[n]
    LAYERS[...] TUNE[...]
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

#: Measured off assets/eve.png: eyes at x=156 and x=594 of 768, both on
#: y=210 of 480, each about 205 across. As fractions, so the rig holds
#: at any size.
EYE_R = 205 / 2 / 768
SPACING = (594 - 156) / 768
EYE_Y = 210 / 480

#: Mouth shapes: the resting height of each segment across the row,
#: sampled at u in 0..1. The voice modulates these; it does not
#: replace them, which is why a smile can talk.
SHAPES: dict[str, Any] = {
    "line":  lambda u: 0.32 + 0.0 * u,
    "smile": lambda u: 0.22 + 0.85 * (1 - (2 * u - 1) ** 2) ** 1.4,
    "frown": lambda u: 0.95 - 0.72 * (1 - (2 * u - 1) ** 2) ** 1.4,
    "o":     lambda u: 0.25 + 1.15 * np.exp(-((u - 0.5) ** 2) / 0.018),
    "wave":  lambda u: 0.45 + 0.35 * np.sin(u * TAU * 1.5),
}

STATES: dict[str, dict] = {
    "idle":     {},
    "happy":    {"tilt": -7, "mouth": "smile", "open": 0.55, "squint": 0.18,
                 "eyecolor": "#9CF0FF"},
    "sad":      {"tilt": 16, "mouth": "frown", "open": 0.35, "gaze": (0, 0.35)},
    "angry":    {"tilt": -26, "mouth": "line", "open": 0.30, "squint": 0.34,
                 "eyecolor": "#7FD8FF", "glow": 1.4},
    "curious":  {"tilt": -4, "roll": 8, "mouth": "o", "open": 0.45,
                 "gaze": (0.3, -0.2)},
    "scanning": {"scan": 1.0, "mouth": "line", "open": 0.25, "squint": 0.1},
    "speaking": {"mouth": "wave", "open": 0.5},
    "sleeping": {"blink": 0.92, "open": 0.16, "glow": 0.5, "dim": 0.65},
}

AIM = {"left": (-0.8, 0.0), "right": (0.8, 0.0), "up": (0.0, -0.7),
       "down": (0.0, 0.7), "center": (0.0, 0.0), "centre": (0.0, 0.0)}


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


def _names(value: Any, fallback: tuple) -> tuple:
    if isinstance(value, str) and value.strip():
        return tuple(p.strip() for p in value.split(",") if p.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(p) for p in value)
    return tuple(fallback)


def _path_from(params: dict) -> Any:
    try:
        from core.tween import path_from
    except ImportError:
        return None
    return path_from(params)


class Eye:
    """One eye. A main circle with an inner gradient, and a TILT.

    Tilt is the control that matters and it is why this is a rotated
    ellipse rather than a disc: a circle turned is still a circle, and
    EVE's whole range is the angle of the shape.
    """

    def __init__(self) -> None:
        self.tilt = 0.0          # degrees, mirrored between the two
        self.gaze = (0.0, 0.0)
        self.blink = 0.0
        self.squint = 0.0
        self.scale = 1.0

    def draw(self, rgb: np.ndarray, cx: float, cy: float, radius: float,
             colour: np.ndarray, side: int, glow: float) -> None:
        radius = radius * max(0.02, self.scale)
        pad = radius * 2.4
        x0 = max(0, int(cx - pad)); x1 = min(rgb.shape[1], int(cx + pad) + 1)
        y0 = max(0, int(cy - pad)); y1 = min(rgb.shape[0], int(cy + pad) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        view = rgb[y0:y1, x0:x1]
        xs = np.arange(x0, x1, dtype=np.float32) - cx + 0.5
        ys = np.arange(y0, y1, dtype=np.float32) - cy + 0.5
        dx = np.broadcast_to(xs[None, :], view.shape[:2]) - self.gaze[0] * radius * 0.22
        dy = np.broadcast_to(ys[:, None], view.shape[:2]) - self.gaze[1] * radius * 0.22

        # Mirrored, so a tilt is a matching pair of angles rather than
        # two eyes leaning the same way, which reads as a head tilt.
        turn = math.radians(self.tilt * side)
        c, s = math.cos(turn), math.sin(turn)
        u, v = dx * c + dy * s, -dx * s + dy * c

        tall = radius * (1.0 - 0.55 * self.squint) * (1.0 - self.blink)
        if tall <= 0.5:
            return
        wide = radius * 0.66
        r = np.sqrt((u / wide) ** 2 + (v / tall) ** 2)

        view += np.clip(1 - r / (2.2 * max(0.2, glow)), 0, 1)[:, :, None] ** 2.5 \
            * colour * 0.16                                   # the eye's own glow
        view += np.clip((1 - r) * min(wide, tall) * 0.5, 0, 1)[:, :, None] \
            * colour * 0.85                                   # the main body
        view += np.clip((0.55 - r) * min(wide, tall), 0, 1)[:, :, None] \
            * colour * 0.55                                   # inner gradient


class Mouth:
    """A row of light segments. The new rig.

    Not a shape that opens on a timer: a SHAPE sets the resting profile
    and the live voice level modulates it, so `smile` while speaking is
    a smile that talks rather than a smile that stops.
    """

    def __init__(self, segments: int = 13) -> None:
        self.segments = max(3, int(segments))
        self.values = np.zeros(self.segments, dtype=np.float32)
        self.shape = "line"
        self.open = 0.4
        self.smooth = 0.4

    def resize(self, segments: int) -> None:
        segments = max(3, int(segments))
        if segments != self.segments:
            self.segments = segments
            self.values = np.zeros(segments, dtype=np.float32)

    def step(self, clock: float, level: float) -> np.ndarray:
        u = (np.arange(self.segments, dtype=np.float32) + 0.5) / self.segments
        profile = np.asarray(
            SHAPES.get(self.shape, SHAPES["line"])(u), dtype=np.float32)
        profile = np.broadcast_to(profile, (self.segments,)).copy()
        if level > 0.02:
            # Speech: the middle moves most, because that is where a
            # mouth opens. A flat multiply makes the whole bar pump,
            # which reads as a graphic equaliser, not a face.
            middle = 1 - np.abs(u - 0.5) * 1.4
            profile = profile * (0.55 + 1.5 * level * np.clip(middle, 0, 1))
            profile *= 1 + 0.12 * np.sin(u * TAU * 3 + clock * 9)
        target = np.clip(profile * self.open, 0.02, 1.6)
        self.values += (target - self.values) * self.smooth
        return self.values


class Eve(Animation):
    """The visor: a glowing panel, two rigged eyes, and a mouth."""

    amplitude_param: float = 0.0

    def __init__(self, width: int, height: int) -> None:
        super().__init__(int(width), int(height))
        self.left, self.right = Eye(), Eye()
        self.mouth = Mouth()
        self.state = "idle"
        self._path = None
        self._move_s = 1.0
        self._level = 0.0
        self.pan = (0.0, 0.0)
        self.scale = 1.0
        self.spacing = 1.0
        self.roll = 0.0
        self.glow = 1.0
        self.texture = 1.0
        self.scan = 0.0
        self.dim = 1.0
        self.speed = 1.0
        self.forced = -1.0
        self.only: tuple = ()
        self.background = (0, 0, 0)
        self.tints = {"eye": (150, 236, 255), "mouth": (226, 250, 255),
                      "panel": (10, 26, 36)}

    @property
    def eyes(self) -> tuple:
        return (self.left, self.right)

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
        self.scale = _number(pick("scale"), preset.get("scale", 1.0))
        self.spacing = _number(pick("spacing"), preset.get("spacing", 1.0))
        self.roll = _number(pick("roll"), preset.get("roll", 0.0))
        self.glow = _number(pick("glow"), preset.get("glow", 1.0))
        self.texture = _number(pick("texture"), preset.get("texture", 1.0))
        self.scan = _number(pick("scan"), preset.get("scan", 0.0))
        self.dim = _number(pick("dim"), preset.get("dim", 1.0))
        self.forced = _number(pick("level"), preset.get("level", -1.0))
        self.only = _names(pick("layers"), preset.get("layers", ()))
        self.background = _rgb(pick("background", "bg"), self.background)
        self.tints["eye"] = _rgb(pick("eyecolor") or preset.get("eyecolor"),
                                 self.tints["eye"])
        self.tints["mouth"] = _rgb(pick("mouthcolor")
                                   or preset.get("mouthcolor"),
                                   self.tints["mouth"])
        self.tints["panel"] = _rgb(pick("color") or preset.get("color"),
                                   self.tints["panel"])

        for eye in self.eyes:
            eye.tilt = _number(pick("tilt"), preset.get("tilt", 0.0))
            eye.gaze = _pair(pick("gaze", "look"),
                             preset.get("gaze", (0.0, 0.0)))
            eye.blink = _number(pick("blink"), preset.get("blink", 0.0))
            eye.squint = _number(pick("squint"), preset.get("squint", 0.0))
            eye.scale = _number(pick("size"), preset.get("size", 1.0))
        wink = str(pick("wink", default="")).strip().lower()
        if wink in ("left", "right"):
            (self.left if wink == "left" else self.right).blink = 1.0

        self.mouth.resize(_number(pick("segs"), preset.get("segs", 13)))
        self.mouth.shape = str(pick("mouth") or preset.get("mouth", "line"))
        self.mouth.open = _number(pick("open"), preset.get("open", 0.4))

    def on_event(self, event: str, **kwargs: Any) -> None:
        if event in STATES:
            self.on_enter(state=event, **kwargs)
        elif event in AIM:
            for eye in self.eyes:
                eye.gaze = AIM[event]
        elif kwargs:
            self.on_enter(state=self.state, **kwargs)

    def level(self) -> float:
        """How loud. Same three rungs as Halo, and the same decay — a
        mouth that snaps shut between chunks chatters."""
        if self.forced >= 0:
            return max(0.0, min(1.0, self.forced))
        live = max(0.0, min(1.0, float(self.amplitude_param or 0.0)))
        self._level = max(live, self._level * 0.80)
        return self._level

    def render_into(self, t: float, frame_rgb: np.ndarray) -> None:
        if self._path is not None:
            self.on_enter(**self._path.at(t / max(1e-6, self._move_s)))
        height, width = frame_rgb.shape[0], frame_rgb.shape[1]
        clock = t * self.speed
        loud = self.level()

        rgb = np.zeros((height, width, 3), dtype=np.float32)
        rgb[:, :] = self.background
        short = min(width, height)
        radius = max(2.0, short * EYE_R * max(0.05, self.scale) * 1.6)
        gap = width * SPACING * 0.5 * self.spacing * max(0.05, self.scale)
        cx = width / 2 + self.pan[0] * width * 0.5
        cy = height * EYE_Y + self.pan[1] * height * 0.5

        eye_ink = np.asarray(self.tints["eye"], dtype=np.float32)
        mouth_ink = np.asarray(self.tints["mouth"], dtype=np.float32)
        panel_ink = np.asarray(self.tints["panel"], dtype=np.float32)

        def wanted(name: str) -> bool:
            return not self.only or name in self.only

        ys = np.arange(height, dtype=np.float32) - cy
        xs = np.arange(width, dtype=np.float32) - cx
        dx = np.broadcast_to(xs[None, :], (height, width))
        dy = np.broadcast_to(ys[:, None], (height, width))
        r = np.sqrt(dx * dx + dy * dy)

        # ── halo: the LARGER circle, a glowing gradient ──
        if wanted("halo"):
            reach = short * 0.62 * self.glow
            rgb += np.clip(1 - r / reach, 0, 1)[:, :, None] ** 2.0 * panel_ink * 3.2
            rgb += np.clip(1 - r / (reach * 0.5), 0, 1)[:, :, None] ** 3.0 \
                * eye_ink * 0.10

        # ── the eyes ──
        if wanted("eyes"):
            roll = math.radians(self.roll)
            for side, eye in zip((-1, 1), self.eyes):
                ex, ey = side * gap, 0.0
                eye.draw(rgb, cx + ex * math.cos(roll) - ey * math.sin(roll),
                         cy + ex * math.sin(roll) + ey * math.cos(roll),
                         radius, eye_ink, side, self.glow)

        # ── the mouth: segments of light under the eyes ──
        if wanted("mouth"):
            bars = self.mouth.step(clock, loud)
            span = gap * 1.5
            my = cy + radius * 2.3
            unit = span * 2 / self.mouth.segments
            for index, value in enumerate(bars):
                bx = cx - span + unit * (index + 0.5)
                half_h = max(0.6, radius * 0.42 * float(value))
                half_w = unit * 0.34
                # A segment's own window. Painting each one across the
                # whole frame is thirteen full-frame passes and was most
                # of the render cost — 22ms down to 3.
                x0 = max(0, int(bx - half_w - 2))
                x1 = min(width, int(bx + half_w + 2) + 1)
                y0 = max(0, int(my - half_h - 2))
                y1 = min(height, int(my + half_h + 2) + 1)
                if x1 <= x0 or y1 <= y0:
                    continue
                sx = np.clip((half_w - np.abs(
                    np.arange(x0, x1, dtype=np.float32) - bx + 0.5)) * 1.6, 0, 1)
                sy = np.clip((half_h - np.abs(
                    np.arange(y0, y1, dtype=np.float32) - my + 0.5)) * 1.6, 0, 1)
                rgb[y0:y1, x0:x1] += (sy[:, None] * sx[None, :])[:, :, None] \
                    * mouth_ink

        # ── texture: the scanline layer that makes it a SCREEN ──
        if wanted("texture") and self.texture > 0.001:
            rows = np.arange(height, dtype=np.float32)
            stripe = 0.86 + 0.14 * np.sign(np.sin(rows * math.pi / 2.0))
            rgb *= (1 - self.texture + self.texture * stripe)[:, None, None]
            if self.scan:
                band = ((clock * 0.35) % 1.0) * height * 1.4 - height * 0.2
                glowline = np.clip(1 - np.abs(rows - band) / (height * 0.05), 0, 1)
                rgb += glowline[:, None, None] * eye_ink * 0.22 * self.scan

        rgb *= max(0.0, self.dim)
        np.clip(rgb, 0, 255, out=rgb)
        frame_rgb[:, :] = rgb.astype(np.uint8)
