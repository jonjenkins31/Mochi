#!/usr/bin/env python3
"""Scaffold per-asset `.props.yaml` sidecars for every animation
that doesn't have one yet.

Writes one sidecar per asset with auto-derived defaults so the
operator can refine the fields manually.  Per
docs/ASSET_PROPERTIES.md.

Usage:
    python tools/scaffold_props.py                # write missing stubs
    python tools/scaffold_props.py --dry-run      # preview only
    python tools/scaffold_props.py --filter gifs  # one type at a time
    python tools/scaffold_props.py --overwrite    # rewrite existing stubs
                                                    (use with care)

A "stub" sidecar contains only the fields whose auto-derived value
is correct.  Fields the operator must decide (ideal_size, framing,
type-specific blocks) are written as commented-out templates so the
file is ready to fill in without remembering the schema.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reuse the catalog builder's plumbing so the renderable filter +
# type table stay in sync.
REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"

sys.path.insert(0, str(REPO_ROOT / "tools"))
from build_catalog import (  # noqa: E402
    RENDERABLE_EXTENSIONS,
    TYPE_CATEGORIES,
    _is_renderable,
    _infer_mood,
    _infer_tags,
    _infer_hint,
    _sidecar_path,
)


# Stub template per type — fields the operator likely wants to set,
# written as commented-out lines for discoverability.  Common header
# is always emitted; the type block is appended when relevant.

COMMON_TEMPLATE = """\
schema: asset-props/v1

# Display name (defaults to filename stem when unset).
# name: "{stem}"

# Authoring credit.
# author: ""
# license: ""
# source_url: ""

# Curation — auto-derived from filename; operator refines.
mood: {mood}
tags: {tags}
hint: "{hint}"

# Rendering hints — uncomment + set when relevant.
# ideal_size: [64, 64]      # [w, h] target display size
# framing: fit              # fit | fill | center | stretch
# playback_speed: 1.0       # 1.0 = native; 2.0 = double speed
# loop: true                # auto-restart at end
# duration_ms: null         # override one-shot stop time

# Operator notes / flags.
# notes: ""
# nsfw: false
"""

TYPE_TEMPLATES = {
    "gifs": """\

# type_props:
#   fps: 24                  # override decoded delays
#   start_frame: 0
#   end_frame: null
#   bg_color: [0, 0, 0]      # behind transparent pixels
""",
    "video": """\

# type_props:
#   fps: 24
#   start_s: 0.0             # trim front
#   end_s: null              # trim back
#   audio: false
""",
    "png": """\

# type_props:
#   # If this PNG is a sprite sheet, declare the grid here:
#   # frame_size: [64, 64]   # [w, h] of each cell
#   # frame_count: 12
#   # grid: [4, 3]           # [cols, rows]
#   # frame_rate_ms: 100
#   # named_frames:
#   #   idle: 0
#   #   walk_1: 1
""",
    "math": """\

# type_props:
#   entry: "render"          # function name in the script
#   period_s: 2.0
#   params:
#     speed:     0.05
#     intensity: 1.0
#   param_schema:
#     speed:     {type: float, min: 0.01, max: 0.5, step: 0.01}
#     intensity: {type: float, min: 0.0,  max: 2.0, step: 0.1}
""",
    "animations": """\

# type_props:
#   blink_interval_ms: 3500
#   pupil_color: [255, 255, 255]
#   bg_color:    [0, 0, 0]
""",
    "mscripts": """\

# type_props:
#   expects_modes: []
#   expected_duration_s: null
#   loop: false
""",
    "bitmaps": """\

# type_props:
#   tint_color: [255, 255, 255]
#   bg_color:   [0, 0, 0]
""",
}


def stub_for(asset: Path, type_: str) -> str:
    """Return the stub yaml text for ``asset`` of ``type_``."""
    stem = asset.stem
    mood = _infer_mood(stem.lower())
    tags = _infer_tags(asset.name, type_)
    hint = _infer_hint(asset.name, type_, mood)
    tag_yaml = "[" + ", ".join(tags) + "]"
    body = COMMON_TEMPLATE.format(
        stem=stem, mood=mood, tags=tag_yaml, hint=hint,
    )
    body += TYPE_TEMPLATES.get(type_, "")
    return body


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="report which sidecars would be written")
    p.add_argument("--filter", type=str, default=None,
                   help=f"limit to one asset type "
                        f"({sorted(RENDERABLE_EXTENSIONS)})")
    p.add_argument("--overwrite", action="store_true",
                   help="rewrite sidecars that already exist "
                        "(default: skip)")
    args = p.parse_args()

    written = 0
    skipped = 0
    would_write: list[Path] = []

    for type_dir, exts in RENDERABLE_EXTENSIONS.items():
        if args.filter and type_dir != args.filter:
            continue
        base = ASSETS_DIR / type_dir
        if not base.is_dir():
            continue
        for asset in sorted(base.rglob("*")):
            if not (asset.is_file() and _is_renderable(asset, type_dir)):
                continue
            sidecar = _sidecar_path(asset)
            if sidecar.exists() and not args.overwrite:
                skipped += 1
                continue
            if args.dry_run:
                would_write.append(sidecar)
                continue
            content = stub_for(asset, type_dir)
            sidecar.write_text(content)
            written += 1

    if args.dry_run:
        print(f"[scaffold] would write {len(would_write)} sidecars")
        for p in would_write[:20]:
            print(f"    {p.relative_to(REPO_ROOT)}")
        if len(would_write) > 20:
            print(f"    ... and {len(would_write) - 20} more")
        print(f"[scaffold] skipped {skipped} that already exist")
        return 0

    print(f"[scaffold] wrote   {written} new sidecars")
    print(f"[scaffold] skipped {skipped} that already existed "
          f"(use --overwrite to rewrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
