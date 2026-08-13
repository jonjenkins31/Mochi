# Mochi Studio — the authoring tool

The original idea: **one window where you make Mochi's content.** Not a
configurator, not a chat client — an IDE for animations.

Shipped in 3.0 as `tools/mochi_studio.py`, now frozen at
`archive/mochi-3.0/tools/mochi_studio.py` (620 lines, Tkinter).

---

## What it does

Three panes, IDE-shaped:

```
┌─ Assets ────┬─ Editors ──────────────┬─ Output & Commands ─┐
│ file tree   │  mscript text editor   │  render output      │
│ + thumbnail │  (line numbers, undo)  │  command entry      │
│ previews    │  sprite editor widget  │  status             │
│             │  bitmap editor widget  │                     │
└─────────────┴────────────────────────┴─────────────────────┘
```

The pieces that carry the value:

| Class | What it is |
|---|---|
| `MscriptTextEditor` | `.mscript` editing with a line-number gutter and undo |
| `SpriteEditorWidget` | drag-to-define sprite rects on a canvas, named frames |
| `BitmapEditorWidget` | 1-bit pixel grid + live preview |
| `AssetPreviewer` | 128px thumbnail cache across gif / png / sprite / bitmap |
| `ResourceEditorDialog` | edits an mscript `[Resources]` key → path mapping |

It imports `core.mscript_engine`, `animations`, and `animations.bitmap_handler`
directly — so the preview it renders is the *real* renderer, not an
approximation. That's the part worth keeping.

Note it shipped **alongside** three standalone editors that do overlapping work:
`sprite_editor_gui.py` (606), `mscript_editor_gui.py` (253),
`bitmap_editor_gui.py` (173). Studio embedded its own copies rather than
reusing them. 1,032 lines of near-duplicate editor across four files was the
tool's real cost.

---

## Where it went

> **Update 2026-08-04 — it went to v5.** `SpriteEditorWidget`,
> `BitmapEditorWidget`, `MscriptTextEditor` and `ResourceEditorDialog` are
> now Qt, in [interfaces/sprite_editor.py](../../../interfaces/sprite_editor.py),
> [interfaces/bitmap_editor.py](../../../interfaces/bitmap_editor.py) and
> [interfaces/mscript_editor.py](../../../interfaces/mscript_editor.py),
> reached from the Characters and MScript Editor tabs. The review below was
> written against the v4 tree and is kept for the reasoning, not the status.
> `AssetPreviewer`'s thumbnail browser is the one piece not carried over.

The v4 tree had:

- **No `tools/` directory** — the editors did not come across.
- **A stub** — Studio's "Editors" tab is a wireframe placeholder
  ([window.py:151](../../mochi/interfaces/studio/window.py#L151)).
- **Four dead tiles** — `v4/mochi_companion.py` still lists
  `tools/mochi_studio.py` and friends as launchable entries
  ([mochi_companion.py:2361-2367](../../mochi/interfaces/v4/mochi_companion.py#L2361-L2367)),
  pointing at paths that no longer exist.

So the *only* working animation-authoring UI in this repository today is the
frozen 3.0 copy, and nothing in the live tree can launch it.

---

## Review

**Keep the idea, don't port the code.** Tk against a Qt app is a dead end, and
the embedded-duplicate-editors structure is exactly what made it 620 lines.

**The renderer coupling is the asset, not the widgets.** Studio was useful
because edit → preview used the shipping decoders. Any Qt replacement has to
keep that loop; a preview that reimplements playback will drift and lie.

**Fastest honest path.** Studio's Editors tab launches the archived tools as
subprocesses — `venv/bin/python archive/mochi-3.0/tools/<editor>.py` (each one
puts its own project root on `sys.path`, so they run in place). Ugly, works
today, turns a stub into a feature without writing an editor. Go native Qt only
when the archive copy actually gets in the way.

**If it does get rewritten**, build one editor with a mode switch, not three —
sprite, bitmap, and mscript are all "grid or timeline over an asset directory."
The 3.0 tool proved they share a shell.

---

## Related

- [ai-studio.md](ai-studio.md) — the shell the Editors tab lives in
- [../ANIMATION_REVIEW.md](../ANIMATION_REVIEW.md) — the pipeline it edits
- [../OPERATOR_PRODUCT_PLAN.md](../OPERATOR_PRODUCT_PLAN.md) §"dev tools" — where this surface sits
