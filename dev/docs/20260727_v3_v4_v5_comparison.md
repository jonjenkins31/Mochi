# Mochi 3.0 → v4 → v5.0

Written 2026-07-27, measured against the archived trees in this repo.

Three attempts at the same product — a virtual character you can run.
The interesting part is not that v5 is smaller. It is *why* v4 got so
large, because that failure is the one the framework exists to prevent.

---

## The numbers

| | .py files | lines | what it was |
|---|---|---|---|
| **3.0** | 76 | 9,528 | a standalone player, all its own |
| **v4** | 458 | 100,773 | a JROS demo app — that had absorbed JROS |
| **v5.0** | 5 | 702 | an app that composes modules |

v5 is **1/135th** of v4. That is not efficiency. It is the difference
between owning a codebase and using one.

---

## 3.0 — the standalone player

```
core/       8 files    ZMQ transport, node base, topics, messages
plugins/   28 files    the adapters: image, gif, sprite, bitmap,
                       video, math, mscript
gui/        7 files    the player windows, control CLI, monitor
tools/      6 files    bitmap/sprite/mscript editors, smoke test
```

**It worked, and it is still readable.** 9.5k lines that do one job
end to end: decode assets, put frames somewhere, show them.

It owned its own transport (`zmq_manager.py`, `topics.py`,
`node_base.py`) because nothing else existed to own it. Every one of
those files has a direct descendant in JaegerOS today — the framework
is, in a real sense, 3.0's `core/` grown up and given to everyone.

**Where it ends:** nothing is shared. A second project wanting the
same face copies the folder. The adapters, which are the genuinely
valuable part, are locked inside one app.

---

## v4 — the fork

```
agent/       153 files   ← an entire agent runtime
interfaces/   61 files
core/         66 files
nodes/        42 files
plugins/      30 files
hardware/     19 files   ← hardware packages, in a desktop character app
skill_tree/    5 files
personality/   4 files
timeline/      3 files
migrations/    1 file
```

v4 was meant to be "Mochi as a JROS app". What it became was **a copy
of JROS with Mochi inside it**. 153 files of agent runtime and 19 of
hardware support, in an app whose job is to draw a face in a window.

This is the failure mode worth naming, because it is not laziness — it
is what happens when the framework has no way to say *"use this,
don't copy it"*:

- No installable modules, so an engine you wanted meant vendoring it.
- No slot binding, so using something meant importing it by path.
- No app manifest, so composition was Python that had to import
  everything it composed.

Once you vendor one thing you vendor its dependencies, and 100k lines
is where that ends. Every one of those copies then drifts from the
original, and a bug fixed upstream is fixed in one place out of two.

**v4 is why the module system exists.** It is not a bad codebase; it
is a good demonstration that "just import it" does not scale to a
second project.

---

## v5.0 — composition

```
main.py               140   flags → JaegerApp(PROJECT_ROOT).run()
jaeger.toml            74   the composition
config.yaml            18
core/characters.py    209   reading a character pack
interfaces/player.py  335   the window
```

Nothing here is transport, node lifecycle, supervision, decoding, or
process management. Those arrive as `jaeger-os` and `jaeger-animation`
— **installed, not copied**.

What is left is exactly what only Mochi could write:

- how to read a character pack and turn "happy" into an atlas cell
- a window that subscribes to frames and blits them
- a manifest saying which capabilities this app needs

That is a good definition of an app tier. If a file here could serve a
second project, it belongs in a module instead.

### What v5 gained over 3.0

- **The adapters are shared.** They live in `jaeger-animation`, so JP01
  and Anima Studio get them. In 3.0 they were 28 files nobody else
  could reach.
- **Subprocess isolation is a config line.** `backend = "zmq"` moves
  nodes into their own processes with no code change. 3.0 had one
  arrangement.
- **Characters are a format, not code.** 3.0's assets were assets; v5's
  packs declare their own vocabulary, so a new character is a folder.
- **Overriding is cheap.** Copy a module into `modules/` and it wins.
  In 3.0 you edited the app; in v4 you edited your fork.

### What v5 has NOT proven

- ~~**3.0's tools are gone.**~~ **Superseded 2026-08-04.** The bitmap,
  sprite and mscript editors were ported to Qt as
  `interfaces/{bitmap,sprite,mscript}_editor.py` and live in the
  Characters and MScript Editor tabs. What did *not* come across:
  `bitmap_editor_gui.py`'s frame-sequence player (a preview, not an
  editor — the media player covers it) and `mochi_studio.py`'s
  thumbnail asset browser.
- **The monitor CLI is gone.** 3.0 had `monitor_cli.py` and
  `control_cli.py`. Both spoke ZMQ to sockets v5 does not open, so
  there was nothing to port — `main.py --nodes` answers the inventory
  half. JaegerOS has a control plane that replaces the rest in
  principle; nobody has driven it from a terminal against Mochi.
- **Nobody has seen the window.** Every claim here is headless.

---

## The one measurement that carried across

**25 of 26** of 3.0's procedural scenes render on v5 unmodified:

```bash
python3 main.py --asset assets/math/wave_scene.py
```

The 26th (`bars.py`) references `self.fg` and never assigns it — broken
in 3.0 too.

That number is the honest parity claim: the rendering half, which is
most of 3.0's value, came through intact and is now shared. The
authoring half followed on 2026-08-04, which is what made deleting the
3.0 tree safe.

---

## What to take from this

The line count is a symptom, not the point. The point is:

- **3.0 owned everything** because there was nothing to own it for
  her. Correct at the time; unshareable.
- **v4 copied everything** because the framework offered no other way
  to use it. That is the failure the module system, slot binding, and
  the app manifest were built to make impossible.
- **v5 composes**, and the test of whether that is real arrives at
  v5.1: adding speech, hearing and a mind should be three manifest
  blocks and **zero lines** in `core/`. If it is not, the composition
  is thinner than it looks.
