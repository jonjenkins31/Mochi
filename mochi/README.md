# Mochi

An embodied AI character — a desktop companion that talks, emotes, and
animates — **and** the test bed where animation / media / avatar **nodes** are
built and proven before they're imported into JROS.

Mochi mirrors the JROS runtime layout (same agent loop, bus, node, and
transport shapes) on purpose: a node built here drops into JROS with a folder
copy + an import-prefix swap (`mochi.` → `jaeger_os.`). Same brain — a body you
can see.

## Layout
- `mochi/` — the runtime: agent loop, tools, memory, **nodes**, transport,
  interfaces, the app chassis.
- `mochi/nodes/` — the nodes (animation, tts, stt, vision, light, motor,
  audio_session) plus the media/animation work this repo exists to grow.
- `archive/mochi-v4/` — the previous Mochi, kept to rebuild the animation
  stack and companion GUI from.

## Run
```
./mochi.sh doctor      # environment / readiness check
./mochi.sh setup       # create an instance (pick a model)
./mochi.sh             # launch
```

See [`MOCHI_GAMEPLAN.md`](../MOCHI_GAMEPLAN.md) for the node roadmap.
