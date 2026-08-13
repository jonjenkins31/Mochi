"""Build playable paired-eye bitmaps from Bitmap Man's legacy sources."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "assets" / "characters" / "bitmap man"
SOURCE = PACK / "assets" / "source"
OUTPUT = PACK / "assets" / "faces"
EYE_GAP = 8


def _pack_rows(pixels: list[int], width: int, height: int) -> list[int]:
    packed: list[int] = []
    for y in range(height):
        row = pixels[y * width:(y + 1) * width]
        for start in range(0, width, 8):
            value = 0
            for bit, pixel in enumerate(row[start:start + 8]):
                if pixel:
                    value |= 1 << (7 - bit)
            packed.append(value)
    return packed


def _pair(left: dict, right: dict) -> dict:
    height = max(int(left["height"]), int(right["height"]))
    left_width = int(left["width"])
    right_width = int(right["width"])
    width = left_width + EYE_GAP + right_width
    pixels = [0] * (width * height)

    for eye, offset_x in ((left, 0), (right, left_width + EYE_GAP)):
        eye_width = int(eye["width"])
        eye_height = int(eye["height"])
        for y in range(eye_height):
            source = y * eye_width
            target = y * width + offset_x
            pixels[target:target + eye_width] = eye["data"][
                source:source + eye_width
            ]

    return {
        "width": width,
        "height": height,
        "data": _pack_rows(pixels, width, height),
    }


def main() -> None:
    animations = json.loads((SOURCE / "2.json").read_text())["animations"]
    sprites = json.loads((SOURCE / "eye_sprites.json").read_text())["sprites"]
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for name, animation in animations.items():
        first = animation["frames"][0]
        payload = _pair(
            sprites[first["left_eye_sprite"]],
            sprites[first["right_eye_sprite"]],
        )
        payload["source_animation"] = name
        (OUTPUT / f"{name}.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
