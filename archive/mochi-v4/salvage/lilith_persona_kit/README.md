# Lilith Persona Kit — salvaged for Mochi

Salvaged from **Lilith-AI** (`archive/src/jaeger_os/instance/lilith/…`) on
2026-06-16, before that app was retired. Lilith was a JROS demo about giving a
local agent a *personality*; this kit is the worth-keeping part of that idea —
the persona/personality subsystem — parked here for Mochi to adopt and adapt.

**Status: salvage, not wired.** Nothing here is imported by Mochi's live code
(`agent/personas/mochi.py` is untouched). The Python modules still import
Lilith/`jaeger_os` internals and won't run as-is — treat them as the reference
implementation of the *idea*. The **JSON personalities** and the **trait→prompt
model** are the directly-reusable parts.

## The core idea: Identity + Persona overlay

Two layers, kept strictly separate:

- **Identity** (`persona_system/identity.py`) — what the agent *is*: its name,
  voice rules (restraint over performance, no cute/emoji/nicknames), self-model.
  Fixed across sessions, hosts, and embodiments. A persona swap never changes it.
- **Persona** (`persona_system/persona.py`) — how it's *tuned*: trait sliders the
  operator (or the agent itself) adjusts to shift expression **without changing
  who it is**. `Persona.to_overlay_block()` renders the sliders into a
  system-prompt block that layers on top of identity.

This separation is the reusable principle: style is a tunable overlay; identity
is not.

## The trait model (four layers)

Each persona is a JSON file (`personas/*.json`) with `meta` + four slider layers
(0.0–1.0):

| Layer | What it tunes |
|---|---|
| **HEXACO** | big-five + honesty-humility (openness, conscientiousness, extraversion, agreeableness, neuroticism, honesty_humility) |
| **S.P.E.C.I.A.L.** | Fallout-style capability sliders (strength, perception, endurance, charisma, intelligence, agility, luck) |
| **Expression** | communication style (sarcasm, warmth, verbosity, formality, directness, …) |
| **Domains** | knowledge-area interest weights |

`meta` carries the non-slider character: `name`, `custom_instructions`,
`speech_patterns`, `backstory`, `category`, `tags`.

## The library — 11 personalities (`personas/`)

`lilith` (the flagship — quiet precision, genuine opinions, not an "assistant"),
plus characters: `glados`, `hal_9000`, `tars`, `bender`, `anakin_skywalker`,
`eren_yeager`, `lelouch`, `paul_atreides`, `helldiver`, and `default_backup`.
Each is a complete trait+meta profile — drop-in examples of the schema.

## The conversational persona skill (`persona_skill/`)

A JROS skill (`manifest.yaml` + `server.py`) that lets the agent adjust **its own**
personality mid-conversation — "be more sarcastic", "tone down the formality",
"what's your personality like right now?". Wraps a `PersonaEditor`:

- `read_traits` — return the live slider values
- `adjust_trait(layer, name, value)` — set one slider
- `bulk_adjust(...)` — several at once

Writes persist to `~/.lilith/profiles/active.json` and fire
`event/persona/changed` on the bus so the live system prompt **rebuilds without a
restart**. (Permission tier 1 — it mutates the active persona file.)

## The GUI ideas (`gui/`)

- **`studio_window.py`** — *Persona Studio*: a live editor for the trait sliders.
- **`radar_chart.py`** — a radar/spider chart that visualizes a persona's trait
  shape (the at-a-glance "personality fingerprint").
- **`_brand.py`** — Lilith's branding/icon helper (PyQt6).

These are **PyQt6**; Mochi's surfaces are PySide6 (like JROS), so porting the
Studio/radar means the same PyQt6→PySide6 + bus-topic adaptation done for the
JROS chat window. The *concept* (edit sliders ▸ see the radar ▸ live prompt
rebuild) is what's worth keeping.

## File map

```
personas/            11 personality profiles (JSON) — the directly-reusable assets
persona_system/
  persona.py         trait-overlay model + library resolution (to_overlay_block)
  identity.py        the fixed identity the persona tunes on top of
persona_skill/       agent-adjustable personas (JROS skill: manifest + server)
gui/                 Persona Studio + radar chart + brand (PyQt6 — needs PySide6 port)
tests/               test_persona.py, test_persona_skill.py (reference behavior)
```

## Porting into Mochi — notes

Mochi today has a single Python persona (`agent/personas/mochi.py`) + a `persona`
string config. This kit upgrades that to a **trait-driven JSON library** with a
conversational editor. A reasonable path:

1. **Assets first** — the 11 `personas/*.json` work as-is; settle on Mochi's
   persona schema (keep the four layers or trim to what Mochi uses).
2. **Model** — adapt `persona.py`'s `to_overlay_block()` to Mochi's prompt
   builder (`agent/loop/runtime.py` / `agent/node.py` already take a `persona`);
   replace Lilith `identity.py` references with Mochi's identity.
3. **Skill** — re-point the skill's bus topic/paths to Mochi's bus + instance
   dir; it's already JROS-skill-shaped.
4. **GUI (optional)** — port Studio + radar to PySide6 if Mochi wants live
   trait editing.

The dependency on `lilith.core.identity` / `jaeger_os.instance.lilith.*` is the
only real friction — everything else is a clean trait-overlay idea.
