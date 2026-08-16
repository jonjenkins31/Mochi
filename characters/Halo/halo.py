"""Halo — a solid core in a reactive ring. Orbs and HAL, crossed.

The third math character, and the first one that answers when you
speak to it.

    HAL gave it   a solid hot core in a dark well, and the rule that a
                  character can be frightening by changing INTENSITY
                  rather than shape
    Orbs gave it  a vocabulary of verbs, and dots arranged by maths
    New here      the RING: bars around the core that rise and fall
                  with the voice, so it is doing something no still
                  image could fake

REACTS TO THE ACTUAL VOICE. `amplitude_param` is set on this object by
the animation node, from `/act/speech/chunk`, while the clip is
running. That hook had existed at one end since 0.5 and nothing ever
called it; wiring it is what makes this character possible at all.

    speaking  the ring follows the amplitude, loudest bars at the
              front, and it decays rather than snapping so a gap
              between chunks is a breath and not a dropout
    thinking  a wave travels around the ring
    idle      the ring breathes, barely

Falling back down the same three rungs the reference design does: real
level, then a proxy, then a pattern. A ring that goes flat the moment
the audio stops looks broken, so it never does.

CONTROLS:

    STATE[listening]   idle watching thinking listening speaking alarm
    CORE[#7BE3B8]      the middle
    COLOR[#8B7CFF]     the ring, at rest
    HOT[#FF7BC8]       the ring, at full — bars blend between them
    BARS[48]           how many
    SIZE[1.2] REACH[1.4] SPIN[n] PULSE[n] GLOW[n] DIM[n]
    LEVEL[0.6]         force the level, for scripting a reaction
                       with no audio present
    PAN[x,y] TILT[deg] LAYERS[...] TUNE[...] SPD[n]
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

#: The core, as a fraction of the shorter side. Smaller than it looks
#: right at first — the ring needs the room, and a big core with a thin
#: ring reads as a button rather than a listener.
CORE = 0.13

STATES: dict[str, dict] = {
    "idle":      {},
    "watching":  {"pulse": 0.10, "rate": 0.5, "glow": 1.15},
    "thinking":  {"mode": "wave", "rate": 2.2, "glow": 1.25, "spin": 1.8},
    "listening": {"mode": "listen", "rate": 1.4, "glow": 1.35,
                  "color": "#57D9A3", "hot": "#8BE8FF"},
    "speaking":  {"mode": "voice", "glow": 1.5},
    "alarm":     {"mode": "wave", "rate": 6.0, "glow": 1.9, "pulse": 0.5,
                  "color": "#FF7B72", "hot": "#FFD166", "core": "#FF7B72"},
    "off":       {"dim": 0.0},
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


def _path_from(params: dict) -> Any:
    try:
        from core.tween import path_from
    except ImportError:
        return None
    return path_from(params)


class Ring:
    """The reactive part. N bars around a circle, each easing toward a
    target the current mode decides.

    Easing rather than assignment is the whole trick: speech arrives in
    chunks with gaps, and a ring that snaps to every value flickers
    while a ring that eases looks like it is listening.
    """

    def __init__(self, bars: int = 44) -> None:
        self.bars = max(6, int(bars))
        self.values = np.zeros(self.bars, dtype=np.float32)
        self.mode = "idle"
        self.rate = 1.0
        self.spin = 1.0
        self.level = 0.0
        self.smooth = 0.35

    def resize(self, bars: int) -> None:
        bars = max(6, int(bars))
        if bars != self.bars:
            self.bars = bars
            self.values = np.zeros(bars, dtype=np.float32)

    def step(self, clock: float, level: float) -> np.ndarray:
        """One frame of targets, then ease toward them."""
        a = np.arange(self.bars, dtype=np.float32) / self.bars
        phase = clock * self.rate
        if self.mode == "voice":
            # Loudest at the front, tapering round the back, so a voice
            # reads as coming FROM the character rather than surrounding
            # it.
            envelope = 0.30 + 0.70 * np.abs(
                np.sin(a * TAU * 2.5 + phase * 1.4))
            front = 0.45 + 0.55 * np.cos((a - 0.5) * TAU / 2) ** 2
            target = level * envelope * front
        elif self.mode == "listen":
            # A slow travelling bump: attention, pointed somewhere.
            bump = np.exp(-((((a - (phase * 0.12 % 1.0)) + 0.5) % 1.0 - 0.5)
                            ** 2) / 0.006)
            target = 0.12 + 0.55 * bump + 0.25 * level
        elif self.mode == "wave":
            target = 0.22 + 0.20 * (0.5 + 0.5 * np.sin(a * TAU * 3 + phase))
        else:
            target = 0.09 + 0.05 * (0.5 + 0.5 * np.sin(
                a * TAU * 2 + phase * 0.4))
        self.values += (target - self.values) * self.smooth
        return np.clip(self.values, 0.0, 1.0)


class Halo(Animation):
    """A solid core, and a ring that answers."""

    #: Set by the animation node from /act/speech/chunk, on the BUS
    #: thread, while this clip is running. The one field here that
    #: something outside writes.
    amplitude_param: float = 0.0

    def __init__(self, width: int, height: int) -> None:
        super().__init__(int(width), int(height))
        self.ring = Ring()
        self.state = "idle"
        self._path = None
        self._move_s = 1.0
        self.pan = (0.0, 0.0)
        self.tilt = 0.0
        self.size = 1.0
        self.reach = 1.0
        self.pulse = 0.16
        self.glow = 1.0
        self.dim = 1.0
        self.bloom = 0.5
        self.speed = 1.0
        self.forced = -1.0          # LEVEL[...] overrides the microphone
        self.only: tuple = ()
        self.background = (0, 0, 0)
        self.tints = {
            "core": (255, 255, 255),
            "field": (139, 124, 255),    # ring at rest
            "hot": (255, 123, 200),      # ring at full
        }
        #: Decays toward zero when no chunk arrives, so a gap between
        #: words is a breath rather than the ring falling over.
        self._level = 0.0

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
        self.size = _number(pick("size"), preset.get("size", 1.0))
        self.reach = _number(pick("reach"), preset.get("reach", 1.0))
        self.pulse = _number(pick("pulse"), preset.get("pulse", 0.16))
        self.glow = _number(pick("glow"), preset.get("glow", 1.0))
        self.dim = _number(pick("dim"), preset.get("dim", 1.0))
        self.bloom = _number(pick("bloom"), preset.get("bloom", 0.5))
        self.forced = _number(pick("level"), preset.get("level", -1.0))
        self.only = _names(pick("layers"), preset.get("layers", ()))
        self.background = _rgb(pick("background", "bg"), self.background)
        for role, token in (("core", "core"), ("field", "color"),
                            ("hot", "hot")):
            self.tints[role] = _rgb(pick(token) or preset.get(token),
                                    self.tints[role])

        self.ring.resize(_number(pick("bars"), preset.get("bars", 44)))
        self.ring.mode = str(pick("mode") or preset.get("mode", "idle"))
        self.ring.rate = _number(pick("rate"), preset.get("rate", 1.0))
        self.ring.spin = _number(pick("spin"), preset.get("spin", 1.0))
        self.ring.smooth = _number(pick("smooth"),
                                   preset.get("smooth", 0.35))

    def on_event(self, event: str, **kwargs: Any) -> None:
        if event in STATES:
            self.on_enter(state=event, **kwargs)
        elif kwargs:
            self.on_enter(state=self.state, **kwargs)

    def level(self) -> float:
        """How loud, right now, down three rungs.

        A forced LEVEL wins, so a script can rehearse a reaction with
        no audio in the room. Otherwise the live amplitude, decayed —
        chunks arrive every few tens of milliseconds and stop dead at
        the end of a word, and a ring that follows that exactly stutters.
        """
        if self.forced >= 0:
            return max(0.0, min(1.0, self.forced))
        live = max(0.0, min(1.0, float(self.amplitude_param or 0.0)))
        self._level = max(live, self._level * 0.82)
        return self._level

    def render_into(self, t: float, frame_rgb: np.ndarray) -> None:
        if self._path is not None:
            self.on_enter(**self._path.at(t / max(1e-6, self._move_s)))
        height, width = frame_rgb.shape[0], frame_rgb.shape[1]
        clock = t * self.speed
        loud = self.level()
        # Speaking is a FACT, not a state you have to declare: if sound
        # is coming out, the ring follows it whatever the script said.
        mode = "voice" if (loud > 0.02 and self.ring.mode in
                           ("idle", "watching")) else self.ring.mode
        was, self.ring.mode = self.ring.mode, mode
        bars = self.ring.step(clock, loud)
        self.ring.mode = was

        core_r = max(2.0, min(width, height) * CORE * 0.5
                     * max(0.05, self.size))
        cx = width / 2 + self.pan[0] * width * 0.5
        cy = height / 2 + self.pan[1] * height * 0.5

        rgb = np.zeros((height, width, 3), dtype=np.float32)
        rgb[:, :] = self.background
        ys = np.arange(height, dtype=np.float32) - cy + 0.5
        xs = np.arange(width, dtype=np.float32) - cx + 0.5
        dx = np.broadcast_to(xs[None, :], (height, width))
        dy = np.broadcast_to(ys[:, None], (height, width))
        r = np.sqrt(dx * dx + dy * dy)
        theta = (np.arctan2(dy, dx) + math.radians(self.tilt)
                 - clock * 0.05 * self.ring.spin) % TAU

        breathe = 1 + self.pulse * math.sin(clock * TAU * 0.35)
        core = np.asarray(self.tints["core"], dtype=np.float32)
        field = np.asarray(self.tints["field"], dtype=np.float32)
        hot = np.asarray(self.tints["hot"], dtype=np.float32)

        def wanted(name: str) -> bool:
            return not self.only or name in self.only

        if wanted("glow"):
            spill = np.clip(1 - r / (core_r * 5.0 * self.glow), 0, 1) ** 2.2
            rgb += spill[:, :, None] * field * 0.20

        if wanted("ring"):
            # Each bar owns an angular slice and stands OUTWARD from a
            # fixed inner edge, so the ring reads as a level meter bent
            # into a circle rather than a wobbling blob.
            index = (theta / TAU * self.ring.bars).astype(np.int32) % self.ring.bars
            height_at = bars[index]
            inner = core_r * 1.9 * self.reach
            outer = inner + core_r * 2.3 * height_at * self.reach
            band = np.clip((outer - r) * 0.7, 0, 1) * np.clip((r - inner) * 0.7, 0, 1)
            # Gaps between bars: without them it is a disc with a ragged
            # edge, and the count stops being legible.
            slot = (theta / TAU * self.ring.bars) % 1.0
            band *= np.clip((0.36 - np.abs(slot - 0.5)) * 7, 0, 1)
            mix = height_at[:, :, None]
            rgb += band[:, :, None] * (field + (hot - field) * mix)

        if wanted("core"):
            rgb += np.clip(core_r * breathe - r + 0.6, 0, 1)[:, :, None] * core
            rgb += np.clip(1 - r / (core_r * 2.1), 0, 1)[:, :, None] ** 2.5 * (
                core * 0.35)

        if self.bloom > 0.001:
            grey = rgb.mean(axis=2)
            pad = max(1, int(core_r * 0.9))
            blurred = grey
            for _ in range(2):
                padded = np.pad(blurred, ((pad, pad), (pad, pad)), mode="edge")
                total = np.pad(np.cumsum(np.cumsum(padded, 0), 1), ((1, 0), (1, 0)))
                size = 2 * pad + 1
                blurred = (total[size:size + height, size:size + width]
                           - total[0:height, size:size + width]
                           - total[size:size + height, 0:width]
                           + total[0:height, 0:width]) / (size * size)
            rgb += blurred[:, :, None] * self.bloom * 0.8
        rgb *= max(0.0, self.dim)
        np.clip(rgb, 0, 255, out=rgb)
        frame_rgb[:, :] = rgb.astype(np.uint8)
