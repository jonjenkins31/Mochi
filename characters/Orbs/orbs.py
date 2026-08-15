"""Orbs — nine dotted thought-orbs, ported from thinking-orbs.

    Original: https://orbs.jakubantalik.com
              https://github.com/Jakubantalik/thinking-orbs
    (c) 2026 Jakub Antalik, MIT. Ported to Python for Mochi's math
    adapter; the geometry is his, the rasteriser is ours.

WHY A PORT AND NOT THE PACKAGE. The library is React on a 2D canvas and
Mochi has no browser in it. What it actually does, though, is arithmetic
— every state is a few hundred DOT POSITIONS computed from `t`, then
filled as circles. That is precisely what a MathScript is, so the maths
crosses over unchanged and only the drawing had to be rewritten.

    npm install thinking-orbs      would have added a runtime we do
                                   not have, to get maths we can read

NINE STATES, ONE PER EXPRESSION. Each is a verb an agent can be doing,
which is why this character is worth having: `orb.state` is the first
Mochi face whose vocabulary is about what the MIND is doing rather than
what a face looks like.

    working     particles on tilted orbits
    searching   a scan meridian sweeps a dotted globe
    solving     bands scramble, then click back solved
    listening   a waveform rolls through the rings
    connecting  a constellation wires itself
    weaving     three strands plait around the sphere
    composing   an undulating multi-band sash
    breathing   a ring slowly morphing
    shaping     dotted outline: circle -> triangle -> square

The state arrives through `on_enter(state=...)`, which is `params:` on
the expression in character.yaml — so all nine live in one file instead
of nine copies of the same engine.

MONOCHROME BY DESIGN, and the original's field name is a trap worth
naming: a dot's `white` is its ink for a LIGHT background. On a dark one
it is inverted, which is why near dots (high depth) end up brightest.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

try:
    # What the animation node hands every math script. The name is an
    # alias the adapter installs while it loads this file, which is why
    # it is not importable any other way.
    from plugin_core.mochi_animations import Animation
except ImportError:  # rendered outside the node — dev/tools/make_cards.py
    class Animation:  # noqa: D101 — the two methods the base really has
        def __init__(self, w: int, h: int) -> None:
            self.w, self.h = w, h

        def on_enter(self, **kwargs: Any) -> None: ...

        def on_event(self, event: str, **kwargs: Any) -> None: ...

        def set_size(self, w: int, h: int) -> None:
            self.w, self.h = w, h

TAU = math.pi * 2

# ── the maths, straight across ───────────────────────────────────


def _rgb(value: Any, fallback: tuple) -> tuple:
    """A colour from anything an operator might reasonably write: three
    numbers, or "#RRGGBB". Anything else keeps what we had — a bad
    colour should not stop the orb drawing."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return tuple(max(0, min(255, int(c))) for c in value)
        except Exception:  # noqa: BLE001
            return fallback
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        try:
            return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return fallback
    return fallback


def _fract(x: float) -> float:
    return x - math.floor(x)


def _hash(x: float, y: float) -> float:
    v = math.sin(x * 12.9898 + y * 78.233) * 43758.5453
    return v - math.floor(v)


def _noise(x: float, y: float) -> float:
    """Value noise with a smoothstep fade — the web state's drift."""
    xi, yi = math.floor(x), math.floor(y)
    fx, fy = x - xi, y - yi
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    a = _hash(xi, yi)
    b = _hash(xi + 1, yi)
    c = _hash(xi, yi + 1)
    d = _hash(xi + 1, yi + 1)
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def _fib(i: int, n: int) -> tuple[float, float, float]:
    """Fibonacci sphere: n points spread evenly, no clumping at poles."""
    step = math.pi * (3 - math.sqrt(5))
    y = 1 - 2 * (i + 0.5) / n
    r = math.sqrt(max(0.0, 1 - y * y))
    a = i * step
    return (r * math.cos(a), y, r * math.sin(a))


def _delta(a: float, b: float) -> float:
    """Shortest signed angle between two headings."""
    return math.atan2(math.sin(a - b), math.cos(a - b))


def _camera(yaw: float, pitch: float, cx: float, cy: float, scale: float):
    """Rotate, project, and land in pixels. Returns (x, y, z)."""
    sp, cp = math.sin(pitch), math.cos(pitch)
    sy, cy_ = math.sin(yaw), math.cos(yaw)

    def project(x: float, y: float, z: float):
        rx = x * cy_ + z * sy
        rz = -x * sy + z * cy_
        ry = y * cp - rz * sp
        rz2 = y * sp + rz * cp
        return (cx + rx * scale, cy - ry * scale, rz2)

    return project


def _rscale(size: int, power: float = 0.6) -> float:
    """Dot radius against canvas size — the original's `(n/300)**p`."""
    return (size / 300.0) ** power


def _finish(dots: list, lines: list, r_min: float = 0.3) -> dict:
    """Drop invisible dots, floor the radius, sort back-to-front."""
    keep = [d for d in dots if d.get("a", 1.0) >= 0.02]
    for d in keep:
        d["r"] = max(r_min, d["r"])
    keep.sort(key=lambda d: d["z"])
    return {"dots": keep,
            "lines": [ln for ln in lines if ln.get("a", 1.0) >= 0.02]}


# ── the nine generators ──────────────────────────────────────────


def _ghost_sphere(project, radius: float, count: int, rs: float) -> list:
    """The faint dotted shell several states sit inside."""
    out = []
    for i in range(count):
        gx, gy, gz = _fib(i, count)
        x, y, z = project(gx * radius, gy * radius, gz * radius)
        depth = (z / radius + 1) / 2
        out.append({"x": x, "y": y, "z": z, "r": 0.8 * rs,
                    "white": 0.78, "a": 0.1 + 0.22 * depth})
    return out


def _braid(size: int, t: float, p: dict) -> dict:
    """weaving — three strands plait around the sphere."""
    cx = cy = size / 2
    radius = size / 2 * 0.76
    project = _camera(t * 0.4, 0.3, cx, cy, 1)
    rs = _rscale(size, p.get("rsPow", 0.6))
    dots = _ghost_sphere(project, radius, int(p.get("ghostN", 150)), rs)

    n = int(p.get("strandN", 52))
    turns = p.get("turns", 3)
    for strand in range(3):
        phase = strand / 3 * TAU
        for i in range(n):
            y = (_fract(i / n + t * 0.045) * 2 - 1) * 0.96
            ring = math.sqrt(max(0.0, 1 - y * y))
            fade = min(1.0, (1 - abs(y)) / 0.1)
            ang = y * math.pi * turns + phase
            swell = 1 + 0.075 * math.sin(
                y * math.pi * turns * 2 + phase * 2 + t * 0.8)
            r = ring * radius * swell
            x, yy, z = project(math.cos(ang) * r, y * radius * swell,
                               math.sin(ang) * r)
            depth = (z / radius + 1) / 2
            dots.append({
                "x": x, "y": yy, "z": z,
                "r": (p.get("rBase", 1.2) + p.get("rDepth", 1.8) * depth) * rs,
                "white": 0.55 - 0.45 * depth,
                "a": fade * (0.45 + 0.55 * depth)})
    return _finish(dots, [], p.get("rMin", 0.3))


def _globe(size: int, t: float, p: dict) -> dict:
    """searching — a scan meridian sweeps a dotted globe."""
    cx = cy = size / 2
    radius = size / 2 * 0.82
    pitch = 0.4 + 0.06 * math.sin(t * 0.35)
    project = _camera(t * 0.5, pitch, cx, cy, radius)
    scan = t * (0.5 + 1.2 * p.get("scanMul", 1))
    rs = _rscale(size, p.get("rsPow", 0.6))
    dim = p.get("dimBase", 1.0)

    dots = []
    rings = int(p.get("latRings", 17))
    density = int(p.get("lonDensity", 44))
    for ring in range(rings + 1):
        lat = -math.pi / 2 + ring / rings * math.pi
        cl, sl = math.cos(lat), math.sin(lat)
        count = max(1, round(abs(cl) * density))
        for i in range(count):
            lon = i / count * TAU
            x, y, z = project(cl * math.cos(lon), sl, cl * math.sin(lon))
            depth = (z + 1) / 2
            near = _delta(lon + t * 0.5, scan)
            lit = math.exp(-(near * near) / 0.18) * max(0.0, z)
            dots.append({
                "x": x, "y": y, "z": z,
                "r": (p.get("rBase", 0.6) + p.get("rDepth", 1.7) * depth
                      + p.get("rBoost", 1) * lit) * rs,
                "white": p.get("inkFar", 0.62) - p.get("inkSpan", 0.54) * depth,
                # dimBase < 1 fades unscanned dots so the meridian reads
                "a": dim + (1 - dim) * min(1.0, lit)})
    return _finish(dots, [], p.get("rMin", 0.3))


def _cuts(count: int) -> list:
    """Deterministic slice planes for the rubik scramble."""
    out = []
    for i in range(count):
        axis = min(2, int(_hash(i, 2.3) * 3))
        lo = -1 + 0.5 * min(3, int(_hash(i, 5.9) * 4))
        sign = 1 if _hash(i, 7.7) < 0.5 else -1
        out.append({"axis": axis, "lo": lo, "hi": lo + 0.5,
                    "ang": sign * math.pi / 2})
    return out


def _schedule(t: float, moves: int, hold: float, rest: float) -> dict:
    """How far through each move we are — out and then back again."""
    period = 2 * moves * hold + rest
    now = t % period
    amount = [0.0] * moves
    active = -1
    if now < 2 * moves * hold:
        step = int(now / hold)
        frac = (now - step * hold) / hold
        eased = 1 - (1 - min(1.0, frac / 0.7)) ** 3
        if step < moves:
            for i in range(step):
                amount[i] = 1.0
            amount[step] = eased
            active = step
        else:
            back = 2 * moves - 1 - step
            for i in range(back):
                amount[i] = 1.0
            amount[back] = 1 - eased
            active = back
    return {"amount": amount, "active": active}


def _twist(point, cuts, sched) -> tuple:
    x, y, z = point
    touched = False
    for i, cut in enumerate(cuts):
        if sched["amount"][i] <= 0:
            continue
        along = x if cut["axis"] == 0 else (y if cut["axis"] == 1 else z)
        if along < cut["lo"] or along >= cut["hi"]:
            continue
        if i == sched["active"]:
            touched = True
        ang = cut["ang"] * sched["amount"][i]
        c, s = math.cos(ang), math.sin(ang)
        if cut["axis"] == 0:
            y, z = y * c - z * s, y * s + z * c
        elif cut["axis"] == 1:
            x, z = x * c + z * s, -x * s + z * c
        else:
            x, y = x * c - y * s, x * s + y * c
    return x, y, z, touched


def _rubik(size: int, t: float, p: dict) -> dict:
    """solving — bands scramble, then click back solved."""
    cx = cy = size / 2
    radius = size / 2 * 0.82
    project = _camera(t * 0.55, 0.35 + 0.1 * math.sin(t * 0.9), cx, cy, radius)
    rs = _rscale(size, p.get("rsPow", 0.6))
    moves = int(p.get("moveCount", 14))
    cuts, sched = _cuts(moves), _schedule(t, moves, 0.42, 1.2)

    dots = []
    rings = int(p.get("latRings", 15))
    density = int(p.get("lonDensity", 40))
    for ring in range(rings + 1):
        lat = -math.pi / 2 + ring / rings * math.pi
        cl, sl = math.cos(lat), math.sin(lat)
        count = max(1, round(abs(cl) * density))
        for i in range(count):
            lon = i / count * TAU
            px, py, pz, hot = _twist(
                (cl * math.cos(lon), sl, cl * math.sin(lon)), cuts, sched)
            x, y, z = project(px, py, pz)
            depth = (z + 1) / 2
            dots.append({
                "x": x, "y": y, "z": z,
                "r": (p.get("rBase", 0.6) + p.get("rDepth", 1.7) * depth
                      + (p.get("rActive", 0.3) if hot else 0)) * rs,
                "white": (p.get("inkFar", 0.62)
                          - p.get("inkSpan", 0.54) * depth
                          - (0.14 if hot else 0))})
    return _finish(dots, [], p.get("rMin", 0.3))


def _wave(size: int, t: float, p: dict) -> dict:
    """listening — a waveform rolls through the rings."""
    cx = cy = size / 2
    radius = size / 2 * 0.874
    project = _camera(t * 0.18, 0.38, cx, cy, 1)
    rs = _rscale(size, p.get("rsPow", 0.6))

    dots = []
    rings = int(p.get("rings", 15))
    density = int(p.get("lonDensity", 40))
    for ring in range(rings + 1):
        lat = -math.pi / 2 + ring / rings * math.pi
        cl, sl = math.cos(lat), math.sin(lat)
        swell = (0.62 * math.sin(t * 2.1 - ring * 0.52)
                 + 0.38 * math.sin(t * 1.27 + ring * 0.83))
        r = radius * (0.88 + 0.105 * swell)
        count = max(1, round(abs(cl) * density))
        for i in range(count):
            lon = i / count * TAU
            x, y, z = project(cl * math.cos(lon) * r, sl * r,
                              cl * math.sin(lon) * r)
            depth = (z / radius + 1) / 2
            crest = max(0.0, swell)
            dots.append({
                "x": x, "y": y, "z": z,
                "r": (p.get("rBase", 0.6) + p.get("rDepth", 1.7) * depth)
                     * (1 + 0.4 * crest) * rs,
                "white": 0.66 - 0.56 * depth - 0.1 * crest})
    return _finish(dots, [], p.get("rMin", 0.3))


def _orbits(size: int, t: float, p: dict) -> dict:
    """working — particles running tilted orbits."""
    cx = cy = size / 2
    radius = size / 2 * 0.82
    project = _camera(t * 0.12, 0.3, cx, cy, 1)
    rs = _rscale(size, p.get("rsPow", 0.6))

    dots = []
    for i in range(int(p.get("orbitN", 12))):
        h1, h2, h3 = _hash(i, 1.7), _hash(i, 5.2), _hash(i, 8.9)
        r = radius * (0.45 + 0.52 * h1)
        lon = h1 * TAU
        lat = math.acos(2 * h2 - 1)
        bx = math.sin(lat) * math.cos(lon)
        by = math.cos(lat)
        bz = math.sin(lat) * math.sin(lon)
        # Two perpendicular vectors spanning this orbit's plane.
        ux, uy, uz = -by, bx, 0.0
        length = max(1e-6, math.hypot(ux, uy))
        ux, uy = ux / length, uy / length
        vx = by * uz - bz * uy
        vy = bz * ux - bx * uz
        vz = bx * uy - by * ux
        speed = (0.25 + 0.55 * h3) * (1 if h3 > 0.5 else -1)

        ghosts = int(p.get("ghostN", 40))
        for g in range(ghosts):
            a = g / ghosts * TAU
            ca, sa = math.cos(a), math.sin(a)
            x, y, z = project((ux * ca + vx * sa) * r,
                              (uy * ca + vy * sa) * r,
                              (uz * ca + vz * sa) * r)
            depth = (z / r + 1) / 2
            dots.append({"x": x, "y": y, "z": z,
                         "r": p.get("ghostR", 0.9) * rs, "white": 0.72,
                         "a": p.get("ghostA", 0.5) * (0.4 + 0.6 * depth)})

        parts = int(p.get("particles", 3))
        for k in range(parts):
            a = t * speed + k / parts * TAU + h2 * 6
            ca, sa = math.cos(a), math.sin(a)
            x, y, z = project((ux * ca + vx * sa) * r,
                              (uy * ca + vy * sa) * r,
                              (uz * ca + vz * sa) * r)
            depth = (z / r + 1) / 2
            dots.append({
                "x": x, "y": y, "z": z,
                "r": (p.get("partR", 1.2)
                      + p.get("partRDepth", 1.6) * depth) * rs,
                "white": 0.3 - 0.22 * depth})
    return _finish(dots, [], p.get("rMin", 0.3))


def _ribbon(size: int, t: float, p: dict) -> dict:
    """composing (a sash) and breathing (`faceOn`, a ring facing you)."""
    cx = cy = size / 2
    radius = size / 2 * 0.78
    spin = p.get("spin", 1)
    pitch = 0.3
    project = _camera(t * 0.1 * spin, pitch, cx, cy, 1)
    rs = _rscale(size, p.get("rsPow", 0.6))
    face_on = bool(p.get("faceOn", 0))

    dots = _ghost_sphere(project, radius, int(p.get("ghostN", 150)), rs)

    yaw = t * 0.24 * spin
    tilt = -pitch if face_on else 0.55 + 0.3 * math.sin(t * 0.18) * spin
    ax, ay, az = math.cos(yaw), 0.0, math.sin(yaw)
    bx = -az * math.sin(tilt)
    by = math.cos(tilt)
    bz = ax * math.sin(tilt)
    nx = ay * bz - az * by
    ny = az * bx - ax * bz
    nz = ax * by - ay * bx

    wob = 0.23 * p.get("wobMul", 1)
    reach = radius / (1 + 0.85 * wob) if face_on else radius
    lanes = max(1, round(int(p.get("lanes", 5)) * p.get("bandMul", 1)))
    segs = int(p.get("segs", 88))
    for lane in range(lanes):
        offset = (lane - (lanes - 1) / 2) * 0.075
        edge = abs(lane - (lanes - 1) / 2) / max(1, (lanes - 1) / 2)
        for i in range(segs):
            a = i / segs * TAU
            undulate = (0.16 * math.sin(a * 3 - t * 1.7 + lane * 0.22)
                        + 0.07 * math.sin(a * 5 + t * 1.1)) * p.get("wobMul", 1)
            swell = 1 + undulate if face_on else 1
            across = offset if face_on else offset + undulate
            ca, sa = math.cos(a), math.sin(a)
            px = ax * ca + bx * sa + nx * across
            py = ay * ca + by * sa + ny * across
            pz = az * ca + bz * sa + nz * across
            norm = math.sqrt(px * px + py * py + pz * pz) or 1e-6
            reach_i = reach * swell
            x, y, z = project(px / norm * reach_i, py / norm * reach_i,
                              pz / norm * reach_i)
            depth = (z / radius + 1) / 2
            dots.append({
                "x": x, "y": y, "z": z,
                "r": (p.get("rBase", 1.1) + p.get("rDepth", 1.7) * depth)
                     * (1 - 0.25 * edge) * rs,
                "white": 0.52 - 0.44 * depth + 0.18 * edge,
                "a": 0.4 + 0.6 * depth})
    return _finish(dots, [], p.get("rMin", 0.3))


def _web(size: int, t: float, p: dict) -> dict:
    """connecting — a constellation wires itself, with signals running."""
    cx = cy = size / 2
    radius = size / 2 * 0.8 * p.get("spread", 1)
    project = _camera(t * 0.12, 0.32, cx, cy, radius)
    rs = _rscale(size, p.get("rsPow", 0.6))
    count = int(p.get("nodeN", 30))
    reach = p.get("thr", 0.72)

    nodes = []
    for i in range(count):
        gx, gy, gz = _fib(i, count)
        gx += 0.3 * (_noise(i * 0.31 + 9, t * 0.24) - 0.5) * 2
        gy += 0.3 * (_noise(i * 0.53 + 27, t * 0.21) - 0.5) * 2
        gz += 0.3 * (_noise(i * 0.77 + 55, t * 0.27) - 0.5) * 2
        norm = math.sqrt(gx * gx + gy * gy + gz * gz) or 1e-6
        nodes.append((gx / norm, gy / norm, gz / norm))

    lines, dots = [], []
    for i in range(count):
        for j in range(i + 1, count):
            dx = nodes[i][0] - nodes[j][0]
            dy = nodes[i][1] - nodes[j][1]
            dz = nodes[i][2] - nodes[j][2]
            gap = math.sqrt(dx * dx + dy * dy + dz * dz)
            if gap >= reach:
                continue
            x1, y1, z1 = project(*nodes[i])
            x2, y2, z2 = project(*nodes[j])
            depth = ((z1 + z2) / 2 + 1) / 2
            lines.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                          "white": 0.42,
                          "a": (1 - gap / reach) * (0.3 + 0.55 * depth),
                          "w": max(0.6, p.get("lineW", 0.8) * rs)})

    node_r = p.get("nodeR", 1.4)
    node_rd = p.get("nodeRDepth", 1.8)
    for i in range(count):
        x, y, z = project(*nodes[i])
        depth = (z + 1) / 2
        pulse = 1 + 0.25 * math.sin(t * 1.4 + i * 2.7)
        dots.append({"x": x, "y": y, "z": z,
                     "r": (node_r + node_rd * depth) * pulse * rs,
                     "white": 0.55 - 0.45 * depth})

    # A few packets in flight between random pairs — the reason this
    # state reads as CONNECTING rather than a static lattice.
    for s in range(int(p.get("signals", 5))):
        seed = math.floor(t * 0.55 + s * 7.31)
        a = int(_hash(seed, s * 3.1 + 1.7) * count)
        b = int(_hash(seed, s * 5.7 + 4.2) * count)
        if a == b:
            continue
        f = _fract(t * 0.55 + s * 7.31)
        px = nodes[a][0] + (nodes[b][0] - nodes[a][0]) * f
        py = nodes[a][1] + (nodes[b][1] - nodes[a][1]) * f
        pz = nodes[a][2] + (nodes[b][2] - nodes[a][2]) * f
        norm = math.sqrt(px * px + py * py + pz * pz) or 1e-6
        x, y, z = project(px / norm, py / norm, pz / norm)
        depth = (z + 1) / 2
        dots.append({"x": x, "y": y, "z": z,
                     "r": (node_r * 1.5 + node_rd * depth) * rs,
                     "white": 0.05, "a": 0.5 + 0.5 * depth})
    return _finish(dots, lines, p.get("rMin", 0.3))


def _walker(points: list):
    """Walk a closed polygon by arc length, so dots stay evenly spaced
    however uneven the shape's edges are."""
    n = len(points)
    lengths, total = [], 0.0
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        lengths.append(d)
        total += d

    def at(u: float):
        want = u * total
        i = 0
        while i < n - 1 and want > lengths[i]:
            want -= lengths[i]
            i += 1
        a, b = points[i], points[(i + 1) % n]
        f = min(1.0, want / lengths[i]) if lengths[i] else 0.0
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)

    return at


def _circle(u: float):
    a = -math.pi / 2 + u * TAU
    return (math.cos(a) * 0.24, math.sin(a) * 0.24)


_TRIANGLE = _walker([(0, -0.26), (0.24, 0.16), (-0.24, 0.16)])
_SQUARE = _walker([(0, -0.2), (0.2, -0.2), (0.2, 0.2), (-0.2, 0.2),
                   (-0.2, -0.2)])
_SHAPES = (_circle, _TRIANGLE, _SQUARE)

_HOLD, _MORPH = 1.4, 0.9


def _shape(size: int, t: float, p: dict) -> dict:
    """shaping — a dotted outline melting circle -> triangle -> square."""
    span = _HOLD + _MORPH
    count = len(_SHAPES)
    now = t % (span * count)
    index = int(now / span)
    into = now - index * span
    blend = 0.0
    if into > _HOLD:
        x = (into - _HOLD) / _MORPH
        blend = x * x * (3 - 2 * x)

    spread = p.get("spread", 1)
    here, nxt = _SHAPES[index], _SHAPES[(index + 1) % count]
    samples = 160
    path = []
    for i in range(samples):
        u = i / samples
        a, b = here(u), nxt(u)
        path.append(((a[0] + (b[0] - a[0]) * blend) * spread,
                     (a[1] + (b[1] - a[1]) * blend) * spread))

    lengths, total = [], 0.0
    for i in range(samples):
        a, b = path[i], path[(i + 1) % samples]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        lengths.append(d)
        total += d

    dot_count = max(6, round(34 * p.get("iconD", 1)))
    r_dot = p.get("rDot", 0.021) * 1.35 * spread
    breathe = 1 + 0.02 * math.sin(into * 3.1)
    half = size / 2
    dots, seg, walked = [], 0, 0.0
    for i in range(dot_count):
        want = i / dot_count * total
        while seg < samples - 1 and walked + lengths[seg] < want:
            walked += lengths[seg]
            seg += 1
        a, b = path[seg], path[(seg + 1) % samples]
        f = min(1.0, (want - walked) / lengths[seg]) if lengths[seg] else 0.0
        x = (a[0] + (b[0] - a[0]) * f) * breathe
        y = (a[1] + (b[1] - a[1]) * f) * breathe
        dots.append({"x": half + x * size, "y": half + y * size, "z": 0,
                     "r": max(0.35, r_dot * size), "white": 0.1})
    return _finish(dots, [], p.get("rMin", 0.25))


#: state -> (generator, profile). The profiles are the library's own
#: `64` presets — its chat-avatar scale, which is what a character face
#: is — with the dot radius left to scale off the real canvas size.
STATES: dict[str, tuple] = {
    "working": (_orbits, {"orbitN": 12, "ghostN": 40, "ghostR": 0.9,
                          "ghostA": 0.5, "particles": 3, "partR": 1.2,
                          "partRDepth": 1.6}),
    "searching": (_globe, {"latRings": 17, "lonDensity": 44, "rBase": 0.6,
                           "rDepth": 1.7, "rBoost": 1, "inkFar": 0.62,
                           "inkSpan": 0.54, "scanMul": 4.08,
                           "dimBase": 0.45}),
    "solving": (_rubik, {"latRings": 15, "lonDensity": 40, "moveCount": 14,
                         "rBase": 0.6, "rDepth": 1.7, "rActive": 0.3,
                         "inkFar": 0.62, "inkSpan": 0.54}),
    "listening": (_wave, {"rings": 15, "lonDensity": 40, "rBase": 0.6,
                          "rDepth": 1.7}),
    "connecting": (_web, {"nodeN": 30, "thr": 0.72, "signals": 5,
                          "nodeR": 1.4, "nodeRDepth": 1.8, "lineW": 0.8}),
    "weaving": (_braid, {"strandN": 52, "turns": 3, "ghostN": 150,
                         "rBase": 1.2, "rDepth": 1.8}),
    "composing": (_ribbon, {"lanes": 5, "segs": 88, "ghostN": 150,
                            "rBase": 1.1, "rDepth": 1.7}),
    "breathing": (_ribbon, {"lanes": 5, "segs": 88, "ghostN": 0,
                            "faceOn": 1, "rBase": 1.1, "rDepth": 1.7}),
    "shaping": (_shape, {"rDot": 0.021, "iconD": 1, "rMin": 0.25}),
}


class Orb(Animation):
    """One thought-orb, drawn into the frame the animation node hands us.

    Deliberately the only class here that the adapter can pick: it takes
    the FIRST `Animation` subclass `dir()` reports, so a second one would
    be a coin toss over which character you get. (`Animation` itself is
    excluded by the adapter, and sorts before `Orb` anyway.)
    """

    #: Filled in by the node when lip-sync is running. Unused: an orb is
    #: a state of mind, and a mouth it does not have cannot flap.
    amplitude_param: float = 0.0

    def __init__(self, width: int, height: int) -> None:
        super().__init__(int(width), int(height))
        self.state = "working"
        self.speed = 1.0
        self.density = 1.0
        self.background = (11, 9, 16)
        #: What the dots are made of. White is the original's monochrome
        #: and stays the default, because a mood colour means nothing if
        #: the resting state already has one.
        self.color = (255, 255, 255)

    def on_enter(self, **kwargs: Any) -> None:
        state = str(kwargs.get("state", self.state)).lower()
        self.state = state if state in STATES else "working"
        self.speed = float(kwargs.get("speed", 1.0))
        self.density = float(kwargs.get("density", 1.0))
        bg = kwargs.get("background")
        if isinstance(bg, (list, tuple)) and len(bg) == 3:
            self.background = tuple(int(c) for c in bg)
        self.color = _rgb(kwargs.get("color"), self.color)

    def on_event(self, event: str, **kwargs: Any) -> None:
        """A scene can switch the orb mid-clip — `working` while it
        thinks, `listening` the moment you start talking. An event may
        also just be a colour, which is how a mood changes without the
        shape changing under it."""
        if event in STATES:
            self.state = event
        self.color = _rgb(kwargs.get("color"), self.color)

    # ── drawing ──────────────────────────────────────────────────

    def render_into(self, t: float, frame_rgb: np.ndarray) -> None:
        height, width = frame_rgb.shape[0], frame_rgb.shape[1]
        frame_rgb[:, :] = self.background

        generator, profile = STATES[self.state]
        params = dict(profile)
        if self.density != 1.0:
            for key in ("ghostN", "strandN", "latRings", "lonDensity",
                        "rings", "orbitN", "nodeN", "segs", "iconD"):
                if key in params:
                    params[key] = max(1, int(params[key] * self.density))

        size = min(width, height)
        scene = generator(size, t * self.speed, params)

        # The orb is drawn square and centred, so a wide display gets
        # bars rather than an oval — an orb that is not round is not an
        # orb.
        ox, oy = (width - size) / 2, (height - size) / 2
        canvas = np.zeros((height, width), dtype=np.float32)
        for line in scene["lines"]:
            self._line(canvas, line, ox, oy)
        for dot in scene["dots"]:
            self._dot(canvas, dot, ox, oy)

        np.clip(canvas, 0.0, 1.0, out=canvas)
        base = np.asarray(self.background, dtype=np.float32)
        ink = np.asarray(self.color, dtype=np.float32)
        # `canvas` is coverage x brightness in one number, so the fade
        # from background to ink IS the shading — no second pass.
        frame_rgb[:, :] = (base + (ink - base) * canvas[:, :, None]
                           ).astype(np.uint8)

    @staticmethod
    def _ink(white: float) -> float:
        """A dot's brightness on a DARK background.

        The original stores `white` as ink for a light background and
        inverts it for dark, which is why 0.55-0.45*depth ends up
        BRIGHTEST at the front. Keeping its convention keeps its tuning.
        """
        return 1.0 - min(1.0, max(0.0, white))

    def _dot(self, canvas: np.ndarray, dot: dict, ox: float, oy: float) -> None:
        """One anti-aliased disc, added into the coverage buffer."""
        r = float(dot["r"])
        cx, cy = float(dot["x"]) + ox, float(dot["y"]) + oy
        value = self._ink(dot["white"]) * float(dot.get("a", 1.0))
        if value <= 0.004:
            return
        pad = r + 1.0
        x0, x1 = int(math.floor(cx - pad)), int(math.ceil(cx + pad))
        y0, y1 = int(math.floor(cy - pad)), int(math.ceil(cy + pad))
        x0, y0 = max(0, x0), max(0, y0)
        x1 = min(canvas.shape[1], x1 + 1)
        y1 = min(canvas.shape[0], y1 + 1)
        if x1 <= x0 or y1 <= y0:
            return
        ys = np.arange(y0, y1, dtype=np.float32) - cy + 0.5
        xs = np.arange(x0, x1, dtype=np.float32) - cx + 0.5
        dist = np.sqrt(xs[None, :] ** 2 + ys[:, None] ** 2)
        # One pixel of feather. Without it a 0.3px dot either vanishes or
        # becomes a hard square, and most of these dots are under a pixel.
        cover = np.clip(r + 0.5 - dist, 0.0, 1.0)
        np.maximum(canvas[y0:y1, x0:x1], cover * value,
                   out=canvas[y0:y1, x0:x1])

    def _line(self, canvas: np.ndarray, line: dict, ox: float,
              oy: float) -> None:
        """A web edge, stamped as a row of discs — cheaper than a real
        line routine and identical at this width."""
        value = self._ink(line["white"]) * float(line.get("a", 1.0))
        if value <= 0.004:
            return
        x1, y1 = float(line["x1"]) + ox, float(line["y1"]) + oy
        x2, y2 = float(line["x2"]) + ox, float(line["y2"]) + oy
        steps = max(2, int(math.hypot(x2 - x1, y2 - y1)))
        half = max(0.4, float(line.get("w", 0.8)) / 2)
        for i in range(steps + 1):
            f = i / steps
            self._dot(canvas, {"x": x1 + (x2 - x1) * f - ox,
                               "y": y1 + (y2 - y1) * f - oy,
                               "r": half, "white": line["white"],
                               "a": line.get("a", 1.0)}, ox, oy)
