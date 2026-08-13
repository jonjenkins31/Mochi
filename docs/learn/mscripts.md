# MochiScript (mscripts)

## What it is

Mochi's scripting DSL for orchestrating multi-step animations: a
sequence of other assets with timing and loops. One operator-authored
file drives a whole performance.

## The language reference

**[`jaeger_animation/docs/MSCRIPT.md`](https://github.com/JenkinsRobotics/JaegerAnimation/blob/main/jaeger_animation/docs/MSCRIPT.md)**
— in JaegerAnimation, because that is where the engine that runs it
lives. Mochi plays motion scripts and edits them; it does not define
them, and a second copy of a spec is a copy that goes stale.

Locally: `../JaegerAnimation/jaeger_animation/docs/MSCRIPT.md`.

## History

- Mochi-specific. Inspired by Fanuc robotics motion programs (per the
  operator's design note) — a concise step-by-step DSL for sequencing.
- 17 scripts in `assets/mscripts/`, plus each character pack's own
  under `characters/<name>/mscripts/`.
- `LBL` / `JMP` loops were specified in v2.0 and implemented in the
  engine on 2026-08-09. Every script written before then still runs
  identically — no label, no change.

## Where it lives now

| Part | Where |
|---|---|
| Language reference | JaegerAnimation `jaeger_animation/docs/MSCRIPT.md` |
| Interpreter | JaegerAnimation `procedural/mscript_engine.py` |
| Command → adapter binding | JaegerAnimation `adapters/mscript_adapter.py` |
| Editor (text + nodes) | Mochi [`interfaces/mscript_editor.py`](../../interfaces/mscript_editor.py) |
| Scripts | `assets/mscripts/*.mscript` |

The older tree this page used to point at — `nodes/animation/plugin_core/`
and `tools/mscript_editor_gui.py` — was v3/v4 and no longer exists.

## Try it

Open the **MScript Editor** tab, pick a motion, press Play. Toggle
**Nodes** to edit the same script as a graph. `demo_wink.mscript` is the
simplest; `demo_sequence.mscript` shows four asset types in one file.

## What's coming

`dev/docs/future_multi_timeline.md` captures the intent to split
mscripts: a general multi-channel timeline (animation + speech + motor
+ light tracks) in a future format, with mscript scoped down to the
motor-channel DSL where its Fanuc-style strengths belong. A follow-up
project, not current scope.
