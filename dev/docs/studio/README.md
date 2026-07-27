# Studio — the idea, three times over

Notes on the **Mochi Studio** and **AI Studio** ideas: what each one actually
is, what exists in the tree today, and how they fit the node architecture in
[MOCHI_GAMEPLAN.md](../MOCHI_GAMEPLAN.md).

- [mochi-studio.md](mochi-studio.md) — the authoring tool (3.0 → today)
- [ai-studio.md](ai-studio.md) — the reference layout that became the v4 shell

---

## The short version

"Studio" has meant three different things in this repo:

| # | Thing | Where | Size | Status |
|---|---|---|---|---|
| 1 | **Mochi Studio (3.0)** — all-in-one Tk authoring tool | `archive/mochi-3.0/tools/mochi_studio.py` | 620 lines | Frozen, runs |
| 2 | **Mochi Companion** — operator configurator, "the 9-page Studio" | `mochi/interfaces/v4/mochi_companion.py` | 4,345 lines | Quarantined, old ZMQ |
| 3 | **Mochi Studio (v4)** — the AI-Studio-shaped shell | `mochi/interfaces/studio/` | 1,369 lines | Live, 4 of 11 pages built |

They are not versions of one program. #1 is a **content authoring tool**, #2 and
#3 are both **product shells** — and #2 and #3 are the same job done twice.

**"AI Studio"** is not one of ours: it's the layout in `reference_ui/` (the
Gemini-generated mockups) that #3 borrowed. [mochi/interfaces/studio/window.py:1](../../mochi/interfaces/studio/window.py#L1)
says so outright — *"the ref_1 'AI Studio' layout, restyled for Mochi."*

---

## How this relates to Mochi

[MOCHI_GAMEPLAN.md](../MOCHI_GAMEPLAN.md) §7 draws the line: nodes (persona,
voice, animation, avatar, media) get imported into JROS; **the product shell
does not**. Studio is Mochi-only. That has one design consequence and the code
already respects it:

> Studio is a **view over the bus**, never a participant in it.

[mochi/interfaces/studio/window.py](../../mochi/interfaces/studio/window.py) is a
pure widget — it exposes `show_frame` / `set_emotion` / `set_status` seams, and
`make_surface(ctx)` is the *only* thing that touches a bus. That's the right
shape: swap the shell without touching a node, swap a node without touching the
shell.

[OPERATOR_PRODUCT_PLAN.md](../OPERATOR_PRODUCT_PLAN.md) split the product into
three surfaces. Mapped onto today's tree:

| Surface | Purpose | Today |
|---|---|---|
| **The toy** | frameless always-on-top character | [mochi/interfaces/avatar_player/](../../mochi/interfaces/avatar_player/) |
| **The configurator** | browse, pick, bind, tune | [mochi/interfaces/studio/](../../mochi/interfaces/studio/) ← *and* `v4/mochi_companion.py` |
| **The dev tools** | sprite / bitmap / mscript editors | **only in `archive/mochi-3.0/tools/`** |

Two of those rows are the problem. The configurator exists twice, and the dev
tools exist only in the 3.0 archive.

---

## Review — what's actually wrong

**1. Two shells, one job.** `studio/` (1,369 lines) and
`v4/mochi_companion.py` (4,345 lines) are both the operator configurator.
Companion is explicitly quarantined — [`mochi/interfaces/v4/__init__.py`](../../mochi/interfaces/v4/__init__.py)
calls it *"imported as-is (quarantine)"* and [launch.py](../../mochi/interfaces/v4/launch.py)
warns its buttons "may be inert until rewired to the new bus." Keep `studio/`:
it's a third the size, bus-agnostic, and on the current bus. Mine companion for
its Library-from-CATALOG grid, Triggers table, and Schedule page, then archive it.

**2. The landing page is blank.** `Dashboard` is `_empty_page()` at stack index
0 ([window.py:142](../../mochi/interfaces/studio/window.py#L142)) — the first
thing Studio shows is nothing. Chat already works; make it the default page.

**3. Shell-first ratio.** 11 nav items, 4 built (one of them empty), 7 wireframe
stubs. The stubs are honest — they say "◌ planned" — but a sidebar that's 64%
placeholder reads as a mockup. Cut the nav to what exists plus the next one or
two; the roadmap belongs in this folder, not in the chrome.

**4. Dead pointers.** Companion's Editors tiles launch `tools/mochi_studio.py`,
`tools/sprite_editor_gui.py`, etc. ([mochi_companion.py:2340-2367](../../mochi/interfaces/v4/mochi_companion.py#L2340-L2367)).
No `tools/` directory exists in the live tree — those four tiles cannot work.

**5. Studio isn't a declared surface.** It's absent from both `mochi.toml` and
`mochi.windowed.toml`. Reachable only from the tray menu
([tray/qt.py:142](../../mochi/interfaces/pyside6/tray/qt.py#L142)) or
`python -m mochi.interfaces.studio`. Fine for now, worth a `[[surface]]` entry
once it's the real front door.

**6. Editors are the actual gap.** The only working sprite / bitmap / mscript
editors in the repo are Tkinter, in `archive/mochi-3.0/tools/`. Studio's
"Editors" tab is a stub. Don't rewrite them in Qt to unstub it — shell out to
the archived ones and get the tab working this week.

---

## Recommendation

1. Delete or archive `v4/mochi_companion.py` after mining Library/Triggers/Schedule.
2. Dashboard → the Chat page (avatar + agent) instead of empty.
3. Nav = Dashboard, Characters, Media, Chat, Animation. Drop the other stubs.
4. Editors tab = subprocess launchers pointing at `archive/mochi-3.0/tools/`.
5. Register Studio as a `[[surface]]` in `mochi.windowed.toml`.

Order matters: (1) and (2) are deletions and cost nothing.
