# Mochi

A virtual character you can run.

Mochi v5 is a **JaegerOS workspace**. It owns no engine code: the face
is rendered by whichever module fills the `animation` slot, and
`jaeger.toml` is the whole composition.

```
/act/display/play  ──▶  animation module  ──▶  /act/display/frame  ──▶  window
```

The window is a subscriber that happens to have pixels in it. It never
calls the engine and never imports it — which is why the same engine
drives an LED matrix and JP01's face without a second code path.

## Run

```bash
./setup.sh                                  # needs python3.11
source venv/bin/activate
python3 main.py                             # the player
python3 main.py --asset ~/clip.gif          # play any file
python3 main.py --character my-pack         # a specific pack
```

## Layout

Same shape as JP01-CC01 — two projects built alike is what makes it a
standard.

```
main.py             JaegerApp(PROJECT_ROOT).run()
jaeger.toml         the composition: bus, nodes, surfaces
config.yaml         settings, per node
core/               this project's own library code
interfaces/         the GUI — player.py
nodes/              nodes this project owns (JP01 has motor, videorx…)
modules/            project modules — SHADOW installed ones
assets/characters/  character packs — drop a folder in, it plays
archive/            mochi-3.0 and mochi-v4, kept, never imported
```

Mochi is a workspace, **not a library**. Nothing imports it; you run it
from this directory. That is why `core/` and `interfaces/` can have
generic names — they never enter anyone's site-packages.

## Nothing you work on is hidden

Installed modules are the default and stay out of sight. When you need
to change one, copy it into `modules/` and yours wins — ROS's workspace
overlay, where `~/ws/src` beats `/opt/ros`. Same rule for characters:
`assets/characters/` beats a module's bundled demo.

Every override is logged. Delete the folder to go back.

See `modules/README.md` for when **not** to use it.

## Characters

A pack is a folder with a `character.yaml` declaring its own
vocabulary — its expressions, its mouth states, its atlas geometry. The
engine knows sprite cells and has never heard of "happy"; Mochi reads
the mapping from the pack.

That boundary is enforced by a test: no feeling may appear as a string
literal in this project's source. Hardcode the word list and you have
written one character into the app forever.

Exporting a pack from Anima Studio into `assets/characters/` is the
whole install step.

## Where v5.0 stops

v5.0 is a **player**: a character on screen, plus any file the engine
has an adapter for. No AI, no microphone, no network — the same thing
Mochi 3.0 was, rebuilt on the framework.

**25 of 26** of Mochi 3.0's procedural scenes render on v5 unmodified:

```bash
python3 main.py --asset archive/mochi-3.0/assets/math/wave_scene.py
```

(The 26th, `bars.py`, uses `self.fg` without ever setting it — broken
in 3.0 too.)

## v5.1

Three more `[[node]]` blocks in `jaeger.toml` — `mind`, `tts`, `stt` —
already sketched there and disabled. **No code in `core/` changes when
they are enabled.** That is the test of whether the composition is
real, and it is worth checking rather than assuming.

The mouth-state axis is what makes it work: hold an expression,
alternate the row, and you have a talking face.
