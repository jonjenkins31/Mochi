# Mochi

A virtual character you can run.

Mochi v5 is a **JaegerOS app**. It owns no engine code: the face is
rendered by whichever module fills the `animation` slot, and
`jaeger.toml` is the entire composition. Swapping the engine, or adding
a voice, is a manifest edit.

```
/act/display/play  ──▶  animation module  ──▶  /act/display/frame  ──▶  window
```

The window is a subscriber that happens to have pixels in it. It never
calls the engine and never imports it — which is why the same engine
drives an LED matrix and JP01's face without a second code path.

## Run it

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m mochi
```

## Where v5.0 stops

v5.0 is a **player**: a character on screen and nothing else. No AI, no
microphone, no network — the same thing Mochi 3.0 was, rebuilt on the
framework. A face that works before a mind that talks.

With no mind attached it walks the character's expressions, which is
also the fastest way to see a pack is wired correctly.

## v5.1

Three more `[[node]]` blocks in `jaeger.toml` — `mind`, `tts`, `stt` —
already sketched there and disabled. **No code in `mochi/` changes when
they are enabled.** That is the test of whether the composition is
real, and it is worth checking rather than assuming.

## Characters

A character is a self-contained folder with a `character.yaml`
declaring its own vocabulary — its expressions, its mouth states, its
atlas geometry. The engine knows about sprite cells and has never heard
of "happy"; Mochi reads the mapping from the pack.

That boundary is enforced by a test: no feeling may appear as a string
literal in `mochi/`. Hardcode the word list and you have written one
character into the app forever.

The demo character ships with JaegerAnimation — 9 expressions × 2 mouth
states, 18 faces. Holding an expression and alternating the mouth row
is what makes it a talking face rather than 18 unrelated pictures.

## History

`archive/mochi-3.0` — the standalone player this design is descended
from. `archive/mochi-v4` — the early JROS demo app v5 replaces.
Both kept; neither is imported.
