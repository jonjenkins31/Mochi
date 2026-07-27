# AI Studio — the reference layout

Not a product of ours and not a thing we're cloning. "AI Studio" is the layout
language in the `reference_ui/` mockups (ref_1) that the current Mochi shell was
built to. [mochi/interfaces/studio/window.py:1](../../mochi/interfaces/studio/window.py#L1)
states the lineage: *"the ref_1 'AI Studio' layout, restyled for Mochi."*

---

## What the layout actually is

The pattern every modern AI web app converged on, and it works because it's
boring:

```
┌─ nav rail ────┬─ center stage ───────────────────────┐
│ logo          │  [ Create ][ Customize ][ Animate ]  │
│               │                                      │
│ Dashboard     │   the thing you're working on        │
│ Characters    │   (avatar / grid / chat)             │
│ Animation     │                                      │
│ …             │   controls under it                  │
│               │                                      │
│ profile card  │                                      │
│ support card  │                                      │
└───────────────┴──────────────────────────────────────┘
```

Three things it gets right, all of which we kept:

- **Persistent nav, swappable center.** [sidebar.py](../../mochi/interfaces/studio/sidebar.py)
  emits `navSelected`; the window swaps a `QStackedWidget`. The sidebar knows
  nothing about any page.
- **Identity is always visible.** The profile card says who you're working as.
  For a character app that's not decoration — it's the whole point.
- **A gradient stage, not a grey form.** [background.py](../../mochi/interfaces/studio/background.py)
  puts a gradient behind everything as a free child widget, resized in
  `resizeEvent`. Swappable overlay, not baked in.

Our restyle: accent `#7C5CFF`, the `theme.py` token set, a 10-swatch character
palette, and the bottom CTA slot repurposed from a premium upsell to a Jenkins
Robotics / YouTube links card ([sidebar.py:51](../../mochi/interfaces/studio/sidebar.py#L51)).

---

## What got built

`mochi/interfaces/studio/` — 1,369 lines across 9 modules:

| Module | Lines | Role |
|---|---|---|
| `characters.py` | 440 | character card grid + trait editor dialog |
| `window.py` | 379 | shell, nav wiring, page stack, render seams |
| `chat.py` | 147 | avatar view + the rich TUI chat, side by side |
| `sidebar.py` | 121 | nav rail, profile card, links card |
| `theme.py` | 121 | color tokens + stylesheet |
| `icons.py`, `background.py`, `__main__.py`, `__init__.py` | 161 | chrome |

**Built:** Media, Characters, Chat. **Empty:** Dashboard.
**Wireframe stubs:** Animation, Editors, Assets, Packs, Diagnostics, Learn,
Settings ([window.py:147-158](../../mochi/interfaces/studio/window.py#L147-L158)).

The Chat page is the one that proves the architecture — the avatar is the
character's card routed *through the animation node* as a single held frame, so
`node → /sense/avatar_frame → view` is a real pipeline from day one
([chat.py:1](../../mochi/interfaces/studio/chat.py#L1)). Richer animation later
is a different clip on the same path, not new plumbing.

---

## Review

**The bus discipline is right and worth protecting.** The window is a pure view;
`make_surface(ctx)` ([window.py:356](../../mochi/interfaces/studio/window.py#L356))
is the single seam that touches the bus. Per
[MOCHI_GAMEPLAN.md](../MOCHI_GAMEPLAN.md) §7 the shell is Mochi-only and never
gets imported into JROS — keeping it bus-agnostic is what makes that true rather
than aspirational. Don't let a page grab a node directly for convenience.

**Adopting a generated mockup wholesale imported its ambition too.** The
reference has a full nav because reference mockups always do. We shipped 11 nav
items against 4 pages. The stubs are labelled honestly, but the ratio is the
tell: the shell got built before the things it's a shell for.

**It duplicates `v4/mochi_companion.py`.** Same job — operator configurator —
4,345 lines of it, on the old ZMQ plane, quarantined. Two shells means every
new page has an ambiguous home. Pick `studio/` and kill the other; see
[README.md](README.md).

**An empty Dashboard is worse than no Dashboard.** Index 0 is `_empty_page()`.
Route it to Chat.

**Not a registered surface.** Absent from `mochi.toml` and
`mochi.windowed.toml`; opened from the tray
([tray/qt.py:142](../../mochi/interfaces/pyside6/tray/qt.py#L142)) or
`python -m mochi.interfaces.studio`. That's deliberate for now — but the tray
holding the only reference means Studio's lifecycle is a side effect of the
tray's, which will bite when it becomes the main window.

---

## Related

- [mochi-studio.md](mochi-studio.md) — what the Editors tab is supposed to contain
- [../OPERATOR_PRODUCT_PLAN.md](../OPERATOR_PRODUCT_PLAN.md) — the three-surface split
- `reference_ui/` — the source mockups (untracked)
