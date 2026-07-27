# assets/characters/

Character packs. **Drop a folder in and it is playable** — that is the
whole install step.

This is what Mochi is for: demoing packs exported from Anima Studio
without a build, a registry, or a code change.

```
assets/characters/
  emotes/                  ← a pack
    character.yaml         what it is, and its own vocabulary
    emotes.png             the atlas
    emotes.props.yaml
```

## What a pack declares

`character.yaml` carries everything needed to play it. The part that
matters is that a character owns its **own vocabulary**:

```yaml
expressions:
  happy:   {column: 6}
  angry:   {column: 2}
mouth_states:
  open:   0        # speaking
  closed: 1        # resting
```

The animation engine knows about sprite cells and has never heard of
"happy". Mochi reads the mapping from here, so a pack with entirely
different words plays through the same code. That boundary is enforced
by a test — no feeling may appear as a string literal in `mochi/`.

The two axes are why this is a grid rather than a strip: holding an
expression and alternating the mouth row **is** the talking animation.

## Project copies win

A pack here shadows one bundled inside an installed module, the same
way `modules/` shadows an installed module. Copy the demo in, edit it,
and yours is what plays:

```bash
cp -a ../JaegerAnimation/jaeger_animation/assets/characters/emotes \
      assets/characters/my-emotes
python3 main.py --character my-emotes
```

`emotes/` here is a project copy of the demo that ships with
JaegerAnimation, placed so the files are visible and editable rather
than buried in a venv.

## Playing one

```bash
python3 main.py                        # the default from config.yaml
python3 main.py --character my-emotes  # a specific pack
```

The picker in the window lists every expression the loaded pack
declares — so a malformed pack shows up as a short list rather than a
crash.
