#!/usr/bin/env python3
"""Generate the Mochi app icon — a Dasai-Mochi-inspired character face.

Operator brief 2026-06-11: "make an app icon inspired by the Dasai
Mochi device we were inspired by... this should be the icon of the
app".

Reproduces the cute red rounded-robot silhouette + dark pixel-face
look from the reference image — but using only Pillow primitives so
the icon is reproducible from this file alone (no external SVG
toolchain, no checked-in binary blobs we can't regenerate).

Outputs:
    assets/icons/mochi_app_icon.png          1024×1024 RGBA
    assets/icons/mochi_app_icon@2x.png       2048×2048 (Retina)
    assets/icons/mochi_app_icon_64.png       64×64 (Dock fallback)

Re-run any time the operator wants to tweak the look:
    python tools/build_app_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = PROJECT_ROOT / "assets" / "icons"


# ── Palette — matches the reference image's saturated red body ────
BODY_RED       = (220, 50, 50, 255)
BODY_HIGHLIGHT = (245, 95, 80, 255)
BODY_SHADOW    = (165, 30, 30, 255)
BODY_BASE_EDGE = (140, 25, 25, 255)
FACE_DARK      = (24, 22, 28, 255)
FACE_EDGE      = (8, 6, 12, 255)
EYE_LIGHT      = (250, 250, 255, 255)
EYE_GLOW       = (180, 230, 240, 220)


def draw_icon(size: int) -> Image.Image:
    """Render a single icon at ``size``×``size``.  All coords are
    expressed in the 1024-grid then scaled, so the look is
    consistent across PNG sizes."""
    g = size / 1024.0  # grid scale
    def s(x: float) -> int:
        return int(round(x * g))

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Body — outer rounded square, shifted slightly down ────────
    # The reference image is "fat at the top, narrows at the base"
    # so we draw three stacked rounded rects to approximate the
    # silhouette without needing a real path.
    body_top_l = (s(70),  s(120))
    body_top_r = (s(954), s(560))
    body_bot_l = (s(110), s(540))
    body_bot_r = (s(914), s(950))

    # Soft drop shadow under the body
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (s(80), s(180), s(944), s(990)),
        radius=s(240), fill=(0, 0, 0, 70),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=s(20)))
    img.paste(shadow, (0, 0), shadow)

    # Base body — wide rounded rect filling most of the canvas
    draw.rounded_rectangle(
        (s(70), s(120), s(954), s(950)),
        radius=s(260), fill=BODY_RED,
    )

    # Bottom shadow band (under-curve)
    band = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    band_draw = ImageDraw.Draw(band)
    band_draw.rounded_rectangle(
        (s(70), s(700), s(954), s(950)),
        radius=s(260), fill=BODY_SHADOW,
    )
    band = band.filter(ImageFilter.GaussianBlur(radius=s(8)))
    img.paste(band, (0, 0), band)
    # Base edge darker line
    draw.rounded_rectangle(
        (s(70), s(920), s(954), s(950)),
        radius=s(40), fill=BODY_BASE_EDGE,
    )

    # ── Top highlight — glossy sheen on the upper half ────────────
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(highlight)
    h_draw.rounded_rectangle(
        (s(160), s(170), s(864), s(420)),
        radius=s(200), fill=BODY_HIGHLIGHT,
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(radius=s(14)))
    img.paste(highlight, (0, 0), highlight)

    # Small bright sheen on top-left
    sheen = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sheen)
    sh_draw.ellipse(
        (s(220), s(190), s(440), s(290)),
        fill=(255, 230, 220, 180),
    )
    sheen = sheen.filter(ImageFilter.GaussianBlur(radius=s(20)))
    img.paste(sheen, (0, 0), sheen)

    # ── Face panel — large dark rounded rectangle ─────────────────
    face_box = (s(180), s(370), s(844), s(800))
    # Outer face frame slightly darker
    draw.rounded_rectangle(face_box, radius=s(90), fill=FACE_EDGE)
    inner = (s(196), s(386), s(828), s(784))
    draw.rounded_rectangle(inner, radius=s(78), fill=FACE_DARK)

    # ── Eyes — pixel-style soft-cornered squares ──────────────────
    eye_y = s(490)
    eye_h = s(150)
    eye_w = s(150)
    eye_gap_from_center = s(80)
    cx = size // 2
    left_eye = (cx - eye_gap_from_center - eye_w, eye_y,
                cx - eye_gap_from_center,         eye_y + eye_h)
    right_eye = (cx + eye_gap_from_center,                 eye_y,
                 cx + eye_gap_from_center + eye_w,         eye_y + eye_h)
    draw.rounded_rectangle(left_eye,  radius=s(28), fill=EYE_LIGHT)
    draw.rounded_rectangle(right_eye, radius=s(28), fill=EYE_LIGHT)

    # Inner highlight in each eye for life
    for box in (left_eye, right_eye):
        x0, y0, x1, y1 = box
        w = x1 - x0
        h = y1 - y0
        hx0 = x0 + int(w * 0.22)
        hy0 = y0 + int(h * 0.18)
        hx1 = x0 + int(w * 0.55)
        hy1 = y0 + int(h * 0.45)
        draw.rounded_rectangle(
            (hx0, hy0, hx1, hy1),
            radius=s(12), fill=EYE_GLOW,
        )

    # ── Smile — soft curved arc below the eyes ────────────────────
    smile_box = (cx - s(140), eye_y + eye_h + s(50),
                 cx + s(140), eye_y + eye_h + s(200))
    draw.arc(smile_box, start=10, end=170,
             fill=EYE_LIGHT, width=s(18))

    return img


def main() -> int:
    ICON_DIR.mkdir(parents=True, exist_ok=True)

    # 1024 baseline
    base = draw_icon(1024)
    base_path = ICON_DIR / "mochi_app_icon.png"
    base.save(base_path, "PNG", optimize=True)
    print(f"  wrote  {base_path}  (1024×1024)")

    # 2048 for Retina / macOS High-DPI Dock
    big = draw_icon(2048)
    big_path = ICON_DIR / "mochi_app_icon@2x.png"
    big.save(big_path, "PNG", optimize=True)
    print(f"  wrote  {big_path}  (2048×2048)")

    # 64 for in-app uses (sidebar mark, etc.)
    small = base.resize((64, 64), Image.LANCZOS)
    small_path = ICON_DIR / "mochi_app_icon_64.png"
    small.save(small_path, "PNG", optimize=True)
    print(f"  wrote  {small_path}  (64×64)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
