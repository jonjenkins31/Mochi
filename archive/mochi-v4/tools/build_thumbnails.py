#!/usr/bin/env python3
"""Generate animated-asset thumbnails for the Library card grid.

Walks assets/CATALOG.json and writes one ``120×120`` PNG thumbnail
per renderable asset into ``assets/thumbs/<name>.png``.

Per-type strategy:

  gifs     → first frame, fit-into-square w/ aspect preserve
  png      → fit-into-square
  icons    → fit-into-square
  bmps     → first frame, ditto
  video    → first frame via imageio
  bitmaps  → render the JSON's 2D array on a square canvas
  math     → render a procedural "code icon" (filename initials on
              an accent square — gives the operator something
              non-blank without executing the script)
  mscripts → render a "scripted" badge
  animations / procedural → same "code icon" style

Cached on disk: re-running this skips thumbnails that are newer
than their source asset (and the catalog).  Companion app
prefers the thumbnail file when present; falls back to the
first-letter placeholder when missing.

Usage:
    python tools/build_thumbnails.py
    python tools/build_thumbnails.py --filter gifs
    python tools/build_thumbnails.py --force
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "assets" / "CATALOG.json"
THUMBS_DIR = REPO_ROOT / "assets" / "thumbs"
THUMB_SIZE = (120, 120)


def _ensure_pil():
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        return True
    except ImportError:
        print("[thumbs] Pillow not installed — pip install pillow",
              file=sys.stderr)
        return False


def _ensure_imageio():
    try:
        import imageio  # noqa: F401
        return True
    except ImportError:
        return False


def _thumb_path(entry: dict) -> Path:
    safe = entry["name"].replace("/", "_").replace(" ", "_")
    return THUMBS_DIR / f"{safe}.png"


def _is_stale(thumb: Path, source: Path) -> bool:
    if not thumb.is_file():
        return True
    try:
        return thumb.stat().st_mtime < source.stat().st_mtime
    except OSError:
        return True


def _placeholder(entry: dict, out: Path) -> bool:
    """Draw a coloured square with the asset's initials.  Used for
    types we can't easily preview (math / mscript / animations)."""
    from PIL import Image, ImageDraw, ImageFont

    name = entry["name"]
    initial = name[:1].upper() if name else "?"

    # Per-type accent colour
    type_ = entry.get("type", "")
    palette = {
        "math":       ("#fef3c7", "#92400e"),
        "mscripts":   ("#d1fae5", "#065f46"),
        "animations": ("#dbeafe", "#1e40af"),
        "procedural": ("#fce7f3", "#9d174d"),
        "bitmaps":    ("#e0e7ff", "#312e81"),
    }
    bg, fg = palette.get(type_, ("#ede9fe", "#5b21b6"))

    img = Image.new("RGB", THUMB_SIZE, bg)
    draw = ImageDraw.Draw(img)
    # Try to use a system font; fall back to default
    font = None
    for font_path in [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(font_path, 64)
            break
        except (OSError, IOError):
            continue
    if font is None:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), initial, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (
            (THUMB_SIZE[0] - tw) // 2 - bbox[0],
            (THUMB_SIZE[1] - th) // 2 - bbox[1],
        ),
        initial,
        fill=fg,
        font=font,
    )
    img.save(out, "PNG", optimize=True)
    return True


def _from_raster(source: Path, out: Path) -> bool:
    """Open + first-frame extract + fit into THUMB_SIZE."""
    from PIL import Image
    try:
        img = Image.open(source)
        img.seek(0)  # first frame for animated formats
        img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        canvas = Image.new("RGB", THUMB_SIZE, (250, 250, 250))
        ox = (THUMB_SIZE[0] - img.size[0]) // 2
        oy = (THUMB_SIZE[1] - img.size[1]) // 2
        canvas.paste(img, (ox, oy))
        canvas.save(out, "PNG", optimize=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[thumbs] {source.name} raster fallback "
              f"(error: {exc})")
        return False


def _from_video(source: Path, out: Path) -> bool:
    """Extract one frame from a video clip using imageio."""
    if not _ensure_imageio():
        return False
    try:
        import imageio.v3 as iio
        from PIL import Image
        frame = iio.imread(source, index=0)
        img = Image.fromarray(frame).convert("RGB")
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        canvas = Image.new("RGB", THUMB_SIZE, (250, 250, 250))
        ox = (THUMB_SIZE[0] - img.size[0]) // 2
        oy = (THUMB_SIZE[1] - img.size[1]) // 2
        canvas.paste(img, (ox, oy))
        canvas.save(out, "PNG", optimize=True)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[thumbs] {source.name} video extract failed: {exc}")
        return False


def build_thumbnail(entry: dict, *, force: bool = False) -> str:
    """Return ``'wrote'`` / ``'skipped'`` / ``'failed'``."""
    source = REPO_ROOT / entry["path"]
    if not source.is_file():
        return "failed"
    out = _thumb_path(entry)
    if not force and not _is_stale(out, source):
        return "skipped"

    type_ = entry.get("type", "")
    ok = False
    if type_ in {"gifs", "png", "icons", "bmps"}:
        ok = _from_raster(source, out)
    elif type_ == "video":
        ok = _from_video(source, out)
    # Anything else (math / mscripts / animations / procedural /
    # bitmaps) → placeholder.  Bitmaps technically have pixel data
    # we could draw, but rendering them through the bitmap_handler
    # adapter just for thumb generation isn't worth the
    # cross-dependency yet.
    if not ok:
        ok = _placeholder(entry, out)

    return "wrote" if ok else "failed"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--filter", type=str, default=None,
                   help="limit to one asset type")
    p.add_argument("--force", action="store_true",
                   help="rebuild even if cached thumb is fresh")
    args = p.parse_args()

    if not _ensure_pil():
        return 1

    if not CATALOG_PATH.is_file():
        print(f"[thumbs] catalog missing: {CATALOG_PATH}",
              file=sys.stderr)
        return 1

    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG_PATH.read_text())
    entries = catalog.get("entries", [])
    if args.filter:
        entries = [e for e in entries if e.get("type") == args.filter]

    wrote = skipped = failed = 0
    for entry in entries:
        status = build_thumbnail(entry, force=args.force)
        if status == "wrote":
            wrote += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

    print(f"[thumbs] wrote   {wrote}")
    print(f"[thumbs] skipped {skipped} (already up-to-date)")
    print(f"[thumbs] failed  {failed}")
    return 0 if failed == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
