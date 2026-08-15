"""Generate the twins' faces — 1-bit packed bitmaps, no dependencies.

    python dev/tools/make_twin_faces.py

Eric and Deborahbot 5000 need a vocabulary before they can perform, and
they need the SAME vocabulary as each other so a two-hander script can
address either of them. Drawn here rather than sourced, because the
point of the pair is testing multi-agent interaction and the art only
has to be legible enough to tell them apart.

    Eric        round eyes  — the one that tries harder to seem human
    Deborahbot  square eyes — the one that does not try at all

Same 72x32, MSB-first packed format the bitmap adapter already reads
(see JaegerAnimation adapters/bitmap_adapter.py), so they cost no new
code path and no new dependency.
"""

from __future__ import annotations

import json
import pathlib

W, H = 72, 32


def blank() -> list[list[int]]:
    return [[0] * W for _ in range(H)]


def rect(px, x0, y0, x1, y1, fill=1):
    for y in range(max(0, y0), min(H, y1 + 1)):
        for x in range(max(0, x0), min(W, x1 + 1)):
            px[y][x] = fill


def disc(px, cx, cy, rx, ry, fill=1):
    for y in range(H):
        for x in range(W):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                px[y][x] = fill


def pack(px) -> list[int]:
    """MSB-first, `width // 8` bytes per row — the adapter's format."""
    data = []
    for row in px:
        for byte in range(W // 8):
            value = 0
            for bit in range(8):
                if row[byte * 8 + bit]:
                    value |= 1 << (7 - bit)
            data.append(value)
    return data


def eye(px, cx, cy, style, shape):
    """One eye. `style` is the character, `shape` the expression."""
    round_ = style == "round"
    if shape == "closed":
        rect(px, cx - 9, cy - 1, cx + 9, cy + 1)
        return
    if shape == "sad":
        cy += 3
    if shape == "up":
        cy -= 4
    if shape == "down":
        cy += 4
    if round_:
        disc(px, cx, cy, 10, 9)
        disc(px, cx, cy, 5, 4, fill=0)          # pupil hole
    else:
        rect(px, cx - 10, cy - 8, cx + 10, cy + 8)
        rect(px, cx - 4, cy - 3, cx + 4, cy + 3, fill=0)
    if shape == "happy":                         # a lower lid, curved up
        rect(px, cx - 11, cy + 4, cx + 11, cy + 10, fill=0)
        rect(px, cx - 9, cy + 3, cx + 9, cy + 4)


def face(style: str, shape: str) -> dict:
    px = blank()
    eye(px, 20, 16, style, shape)
    eye(px, 52, 16, style, shape)
    return {"width": W, "height": H, "data": pack(px),
            "source_animation": shape}


FACES = {"neutral": "neutral", "happy": "happy", "closed": "closed",
         "look_up": "up", "look_down": "down", "sad": "sad"}


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2] / "characters"
    for folder, style in (("Eric", "round"), ("Deborahbot 5000", "square")):
        out = root / folder / "assets" / "faces"
        out.mkdir(parents=True, exist_ok=True)
        for name, shape in FACES.items():
            (out / f"{name}.json").write_text(
                json.dumps(face(style, shape)))
        print(f"  {folder:18} {len(FACES)} faces -> {out.relative_to(root.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
