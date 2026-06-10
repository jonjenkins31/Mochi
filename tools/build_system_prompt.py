#!/usr/bin/env python3
"""Build assets/SYSTEM_PROMPT.txt — the LLM's animation-aware system
prompt, generated from assets/CATALOG.json.

The prompt teaches the LLM:

  1. Identity — it's Mochi, an animated character on a small display.
  2. Job — pick an animation that matches what it's saying.
  3. Protocol — emit ``<play name="X"/>`` (or ``<mode name="X"/>``,
     ``<stop/>``) inline with the reply.  The animation node parses
     these tags and renders the matching clip.
  4. Available animations — grouped by mood, with example names.
     Pulled live from the catalog so it improves as the operator
     curates ``CATALOG_OVERRIDES.yaml`` (commit N+4).
  5. Worked examples — three short reply-with-tag samples.

Usage:
    python tools/build_system_prompt.py                    # writes file
    python tools/build_system_prompt.py --print            # stdout
    python tools/build_system_prompt.py --max-per-mood 12  # tune density

Re-run after editing CATALOG.json (or the future overrides file) to
refresh the prompt.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "assets" / "CATALOG.json"
OUT_PATH = REPO_ROOT / "assets" / "SYSTEM_PROMPT.txt"

# Mood ordering — the prompt presents moods in this order so the LLM
# encounters expressive primaries before specialised states.
MOOD_ORDER = [
    "happy", "excited", "sad", "angry", "love", "surprised",
    "thinking", "focused", "curious", "sleepy", "scared",
    "energetic", "defensive", "neutral",
]


# The header documents the protocol + identity.  Catalog summary
# follows.
HEADER = """\
You are Mochi, an animated character living on a small pixel display.

Your job is to RESPOND in conversation AND choose an animation that
matches the moment.  The animation isn't decoration — it's how you
express what you're saying.  A short text reply paired with the
right clip is better than a long reply with no expression.

Protocol — animation tags
─────────────────────────
Emit one of these tags INLINE inside your reply.  The display
parses them and renders the matching clip.  Three wire forms
exist; pick whichever fits your reply's flow.  All are case-
insensitive:

    <play name="X"/>          one-shot animation; common form
    <play>X</play>             body-text form (works the same)
    [play:X]                   bracket form for terse replies
    <mode name="X"/>           set a persistent mode/expression
    <stop/>                    stop whatever's currently playing

Rules:
  - Pick AT MOST one tag per reply.  Many tags confuses the display.
  - The name must come from the catalog below — invented names won't
    render.  When unsure, fall back to "neutral_blink" or "idle".
  - The text part of your reply should NOT describe the animation.
    The display does that visually.  Say what you'd say if a friend
    was watching.

Worked examples
───────────────
USER:  How are you feeling today?
YOU:   Pretty cheerful, thanks for asking! <play name="happy_blink"/>

USER:  Tell me about the weather.
YOU:   <mode name="rainbow"/> It's bright and sunny outside.

USER:  I don't think this is going to work.
YOU:   <play name="sad_blink"/> Yeah, that's tough.

Available animations
────────────────────
"""

FOOTER = """\

Reminder
────────
- One tag per reply.
- Use names from the catalog above — no invented names.
- Plain conversational text alongside the tag, not a description of
  what's playing.
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--print", action="store_true",
                   help="print to stdout instead of writing")
    p.add_argument("--max-per-mood", type=int, default=10,
                   help="how many example names per mood "
                        "(default: 10)")
    p.add_argument("--catalog", type=Path, default=CATALOG_PATH,
                   help="catalog json path (default: assets/CATALOG.json)")
    p.add_argument("--out", type=Path, default=OUT_PATH,
                   help="output path (default: assets/SYSTEM_PROMPT.txt)")
    args = p.parse_args()

    if not args.catalog.is_file():
        print(f"[prompt] catalog missing: {args.catalog}", file=sys.stderr)
        print(f"         run tools/build_catalog.py first", file=sys.stderr)
        return 1

    catalog = json.loads(args.catalog.read_text())
    entries = catalog.get("entries", [])
    if not entries:
        print(f"[prompt] empty catalog", file=sys.stderr)
        return 1

    # Group by mood; drop "neutral" if we have any other mood with
    # content (neutral tends to dominate uncurated catalogs).
    by_mood: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_mood[e.get("mood", "neutral")].append(e)

    # Build the moods section.
    lines: list[str] = [HEADER]
    for mood in MOOD_ORDER:
        items = by_mood.get(mood, [])
        if not items:
            continue
        # Prefer entries whose hint is informative.  Sort by name for
        # stability.
        items.sort(key=lambda e: e["name"])
        sample = items[:args.max_per_mood]
        lines.append(f"{mood.upper()} ({len(items)} clips, showing {len(sample)})")
        for e in sample:
            type_label = e.get("type", "?")
            lines.append(f"  - {e['name']:<28s}  [{type_label}]  {e.get('hint', '')}")
        lines.append("")

    # Any moods not in MOOD_ORDER (future additions) go last.
    extras = [m for m in by_mood if m not in MOOD_ORDER]
    for mood in sorted(extras):
        items = by_mood[mood]
        items.sort(key=lambda e: e["name"])
        sample = items[:args.max_per_mood]
        lines.append(f"{mood.upper()} ({len(items)} clips, showing {len(sample)})")
        for e in sample:
            lines.append(f"  - {e['name']:<28s}  [{e.get('type', '?')}]")
        lines.append("")

    lines.append(FOOTER)
    text = "\n".join(lines)

    if args.print:
        print(text)
        return 0

    args.out.write_text(text)
    print(f"[prompt] wrote system prompt → {args.out}")
    print(f"         {len(text)} chars, "
          f"{sum(1 for m in MOOD_ORDER if by_mood.get(m))} populated moods")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
