#!/usr/bin/env python3
"""Build assets/CATALOG.json — a structured index of every
renderable animation in the Mochi asset library.

The catalog is what the LLM reads to know what's available.  Without
it, the LLM has nothing to pick FROM.

Usage:
    python tools/build_catalog.py                      # writes CATALOG.json
    python tools/build_catalog.py --print              # stdout (no write)
    python tools/build_catalog.py --dry-run            # what would change
    python tools/build_catalog.py --filter gif         # only the GIF tree
    python tools/build_catalog.py --merge-overrides    # honour CATALOG_OVERRIDES.yaml

Catalog entry shape:
    {
      "name":     "happy_blink",         # filename minus extension
      "type":     "animations",          # asset/<type>/<name>
      "path":     "assets/animations/happy_blink.json",
      "size_b":   1234,
      "category": "eye_animation",       # inferred from type + name
      "mood":     "happy",               # inferred from filename tokens
      "tags":     ["eye", "blink", "happy"],
      "hint":     "Quick happy eye blink — use for short positive reactions"
    }

mood + tags + hint are AUTO-DERIVED.  Operator can hand-curate
overrides via assets/CATALOG_OVERRIDES.yaml (followup commit; for
now the generator stands on its own).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
CATALOG_PATH = ASSETS_DIR / "CATALOG.json"
OVERRIDES_PATH = ASSETS_DIR / "CATALOG_OVERRIDES.yaml"

# Asset roots → renderable extensions for that handler type.
RENDERABLE_EXTENSIONS: dict[str, set[str]] = {
    "animations":  {".json"},                          # eye-animation defs
    "bitmaps":     {".json"},                          # 1-bit bitmap defs
    "bmps":        {".bmp"},                           # raw bitmaps
    "gifs":        {".gif"},
    "icons":       {".png", ".bmp"},
    "math":        {".py"},                            # procedural scripts
    "mscripts":    {".msc", ".mscript", ".txt"},
    "png":         {".png"},
    "procedural":  {".py", ".json"},
    "video":       {".mp4", ".webm", ".mov", ".m4v"},
}

# Type → human category label for the LLM's catalog read.
TYPE_CATEGORIES: dict[str, str] = {
    "animations":  "eye_animation",
    "bitmaps":     "static_bitmap",
    "bmps":        "static_bitmap",
    "gifs":        "looping_gif",
    "icons":       "icon",
    "math":        "procedural_script",
    "mscripts":    "scripted_sequence",
    "png":         "static_image",
    "procedural":  "procedural_script",
    "video":       "video_clip",
}

# Mood keywords — first match wins; case-insensitive substring of the
# filename stem (the part before the extension).  Operator extends in
# a sidecar later.
MOOD_KEYWORDS: list[tuple[str, str]] = [
    ("happy",     "happy"),
    ("smile",     "happy"),
    ("laugh",     "happy"),
    ("cheer",     "happy"),
    ("excited",   "excited"),
    ("party",     "excited"),
    ("dance",     "excited"),
    ("sad",       "sad"),
    ("cry",       "sad"),
    ("frown",     "sad"),
    ("tear",      "sad"),
    ("angry",     "angry"),
    ("mad",       "angry"),
    ("rage",      "angry"),
    ("fight",     "angry"),
    ("punch",     "angry"),
    ("attack",    "angry"),
    ("knife",     "angry"),
    ("sword",     "angry"),
    ("slash",     "angry"),
    ("sleep",     "sleepy"),
    ("doze",      "sleepy"),
    ("yawn",      "sleepy"),
    ("tired",     "sleepy"),
    ("blink",     "neutral"),
    ("neutral",   "neutral"),
    ("idle",      "neutral"),
    ("wait",      "neutral"),
    ("look",      "curious"),
    ("watch",     "curious"),
    ("curious",   "curious"),
    ("think",     "thinking"),
    ("ponder",    "thinking"),
    ("wonder",    "thinking"),
    ("focused",   "focused"),
    ("focus",     "focused"),
    ("scared",    "scared"),
    ("fear",      "scared"),
    ("afraid",    "scared"),
    ("love",      "love"),
    ("heart",     "love"),
    ("kiss",      "love"),
    ("surprise",  "surprised"),
    ("shock",     "surprised"),
    ("wow",       "surprised"),
    ("run",       "energetic"),
    ("walk",      "energetic"),
    ("jump",      "energetic"),
    ("shield",    "defensive"),
    ("block",     "defensive"),
    ("crouch",    "defensive"),
]

# Tag inference — phrases that should land in the tag list (in addition
# to mood).  Looser than mood keywords; catches descriptive bits.
TAG_KEYWORDS: list[str] = [
    "eye", "face", "mouth", "blink", "wink", "smile", "frown", "tongue",
    "happy", "sad", "angry", "neutral", "focused", "thinking", "sleepy",
    "love", "heart", "kiss", "surprised", "shock",
    "run", "walk", "jump", "punch", "fight", "shield", "crouch",
    "weather", "rain", "snow", "sun", "moon",
    "robot", "monster", "knight", "goblin", "dino",
    "logo", "spotify", "rainbow", "rgb", "test", "demo",
    "idle", "look", "watch", "wait",
    "static", "loop", "scripted", "procedural",
    "weapon", "sword", "knife", "whip", "shield",
    "background", "bg",
]


def _stem_tokens(name: str) -> list[str]:
    """Split a filename stem into lowercase tokens for matching."""
    stem = Path(name).stem.lower()
    # split on _ - . space + camelCase boundaries
    stem = re.sub(r"([a-z])([A-Z])", r"\1_\2", Path(name).stem)
    stem = stem.lower()
    return [t for t in re.split(r"[_\-\.\s]+", stem) if t]


def _infer_mood(stem_lower: str) -> str:
    for needle, mood in MOOD_KEYWORDS:
        if needle in stem_lower:
            return mood
    return "neutral"


def _infer_tags(name: str, type_: str) -> list[str]:
    stem_lower = Path(name).stem.lower()
    tokens = set(_stem_tokens(name))
    out: list[str] = []
    # Mood is always a tag.
    out.append(_infer_mood(stem_lower))
    # Type-derived structural tag.
    out.append(type_)
    # Token-match keywords.
    for tag in TAG_KEYWORDS:
        if tag in tokens or tag in stem_lower:
            if tag not in out:
                out.append(tag)
    return out


def _infer_hint(name: str, type_: str, mood: str) -> str:
    """Build a one-line LLM-readable hint."""
    stem = Path(name).stem
    if type_ == "animations":
        return f"{mood.title()} eye animation ({stem})."
    if type_ == "math":
        return f"Procedural Python animation: {stem}."
    if type_ == "gifs":
        return f"{mood.title()} GIF clip ({stem})."
    if type_ == "video":
        return f"{mood.title()} video clip ({stem})."
    if type_ == "mscripts":
        return f"Scripted sequence: {stem}."
    if type_ == "bitmaps":
        return f"1-bit bitmap: {stem}."
    if type_ == "png":
        return f"Static PNG image: {stem}."
    return f"{type_}: {stem}."


def _is_renderable(path: Path, type_: str) -> bool:
    if path.name.startswith("."):
        return False
    if "__pycache__" in path.parts:
        return False
    if path.name.endswith(".props.yaml"):
        # Sidecars are not renderable themselves — handled separately.
        return False
    exts = RENDERABLE_EXTENSIONS.get(type_, set())
    return path.suffix.lower() in exts


def _sidecar_path(asset: Path) -> Path:
    """Return the conventional sidecar path for an asset.

    ``assets/gifs/happy.gif`` → ``assets/gifs/happy.props.yaml``
    See docs/ASSET_PROPERTIES.md for the schema.
    """
    return asset.with_suffix(asset.suffix + ".props.yaml") if False else \
           asset.with_name(asset.stem + ".props.yaml")


def _load_sidecar(asset: Path) -> dict[str, Any]:
    """Load the asset's `.props.yaml` sidecar if present.  Returns
    an empty dict when the sidecar is missing, malformed, or yaml
    isn't installed (build_catalog must still work in minimal envs).
    """
    sidecar = _sidecar_path(asset)
    if not sidecar.is_file():
        return {}
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(sidecar.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def build_entry(asset: Path, type_: str) -> dict[str, Any]:
    rel = asset.relative_to(REPO_ROOT)
    stem = asset.stem
    auto_mood = _infer_mood(stem.lower())
    auto_tags = _infer_tags(asset.name, type_)
    try:
        size_b = asset.stat().st_size
    except OSError:
        size_b = 0

    # Auto-derived defaults — every field can be overridden by the
    # sidecar.  See docs/ASSET_PROPERTIES.md for the full schema.
    entry: dict[str, Any] = {
        "name":     stem,
        "type":     type_,
        "path":     str(rel),
        "size_b":   size_b,
        "category": TYPE_CATEGORIES.get(type_, "unknown"),
        "mood":     auto_mood,
        "tags":     auto_tags,
        "hint":     _infer_hint(asset.name, type_, auto_mood),
    }

    sidecar = _load_sidecar(asset)
    if not sidecar:
        entry["has_sidecar"] = False
        return entry
    entry["has_sidecar"] = True

    # Curation overrides (sidecar wins).
    for key in ("name", "mood", "hint", "tags",
                "author", "license", "source_url",
                "ideal_size", "framing", "playback_speed",
                "loop", "duration_ms", "notes", "nsfw"):
        if key in sidecar:
            entry[key] = sidecar[key]

    # Type-specific block lives under `type_props`.
    if "type_props" in sidecar and isinstance(sidecar["type_props"], dict):
        entry["type_props"] = sidecar["type_props"]

    return entry


def walk_assets(filter_type: str | None = None) -> list[dict[str, Any]]:
    """Walk every recognised asset directory and yield catalog entries.

    Sorted by (type, name) for stable diffs.
    """
    entries: list[dict[str, Any]] = []
    for type_dir, exts in RENDERABLE_EXTENSIONS.items():
        if filter_type and type_dir != filter_type:
            continue
        base = ASSETS_DIR / type_dir
        if not base.is_dir():
            continue
        for asset in sorted(base.rglob("*")):
            if asset.is_file() and _is_renderable(asset, type_dir):
                entries.append(build_entry(asset, type_dir))
    entries.sort(key=lambda e: (e["type"], e["name"]))
    return entries


def write_catalog(
    entries: list[dict[str, Any]],
    dest: Path = CATALOG_PATH,
) -> None:
    catalog = {
        "version": 1,
        "generator": "tools/build_catalog.py",
        "asset_count": len(entries),
        "by_type": _count_by_key(entries, "type"),
        "by_mood": _count_by_key(entries, "mood"),
        "entries": entries,
    }
    dest.write_text(json.dumps(catalog, indent=2) + "\n")


def _count_by_key(entries: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in entries:
        v = e.get(key, "unknown")
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--print", action="store_true",
                   help="print to stdout instead of writing CATALOG.json")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would change without writing")
    p.add_argument("--filter", type=str, default=None,
                   help=f"limit to one asset type (e.g. gifs, math). "
                        f"Choices: {sorted(RENDERABLE_EXTENSIONS)}")
    args = p.parse_args()

    entries = walk_assets(filter_type=args.filter)
    if not entries:
        print("[catalog] no renderable assets found", file=sys.stderr)
        return 1

    if args.print:
        print(json.dumps({
            "asset_count": len(entries),
            "by_type": _count_by_key(entries, "type"),
            "by_mood": _count_by_key(entries, "mood"),
            "entries": entries,
        }, indent=2))
        return 0

    if args.dry_run:
        print(f"[catalog] would write {len(entries)} entries → {CATALOG_PATH}")
        print(f"          by type:  {_count_by_key(entries, 'type')}")
        print(f"          by mood:  {_count_by_key(entries, 'mood')}")
        return 0

    write_catalog(entries)
    print(f"[catalog] wrote {len(entries)} entries → {CATALOG_PATH}")
    print(f"          by type:  {_count_by_key(entries, 'type')}")
    print(f"          by mood:  {_count_by_key(entries, 'mood')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
