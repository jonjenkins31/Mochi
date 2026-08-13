# characters/

Character packs. **Drop a folder in and it is playable** — that is the
whole install step.

This is what Mochi is for: demoing packs exported from Anima Studio
without a build, a registry, or a code change.

Every character folder containing renderable assets follows the same shape:

```
characters/
  <character>/
    character.yaml         required identity + render contract
    README.md              optional attribution and authoring notes
    mscripts/              character-owned motion sequences
      <motion>.mscript
    assets/
      <asset>              images, sheets, clips, scripts, or rigs
      <asset>.props.yaml   optional layout/playback metadata
```

A directory without `character.yaml` is not a character and is ignored. This
is intentional for empty staging directories: a manifest must never point at
an asset that does not exist.

## Standard character manifest

Every `character.yaml` declares the same core fields:

```yaml
schema: character/v1
character: example
name: "Example"
kind: sprite_sheet             # sprite_sheet | clip_set | procedural | rig

assets:
  primary:
    file: assets/face.png      # use root: for a clip collection
    type: sprite_sheet
    adapter: sprite            # sprite | image | video | gif | math | mscript
    properties: assets/face.props.yaml
    layout: grid               # grid | regions, for sprite sheets
default_asset: primary

motion_scripts:
  root: mscripts
  default: mscripts/idle.mscript

# Active/default rendering declaration for character/v1 consumers.
render:
  adapter: sprite
  asset: assets/face.png
  grid: [9, 2]

expressions:
  happy: {column: 0}
default_expression: happy
```

`kind` says what the character fundamentally is. `adapter` says which engine
adapter renders a particular asset:

| Character kind | Typical adapters | Addressing in `expressions` |
|---|---|---|
| `sprite_sheet` | `sprite` | `column` + mouth row, flat `cell`, or explicit `src` rectangle |
| `clip_set` | `video`, `gif`, `image` | `clips` keyed by declared state |
| `procedural` | `math`, `mscript` | `params` passed to the procedural asset |
| `rig` | rig-specific adapter | named rig expressions/clips |

The physical shape of an atlas is not part of character identity. Uniform
sheets use `grid`/`cell`; irregular sheets use
`src: [x, y, width, height]`. Both resolve to the same sprite adapter.

## Motion scripts

Every character pack carries an `mscripts/` directory. The manifest's
optional `motion_scripts` block points at that directory and names the
sequence to offer first. A motion script is not another character format: it
is a preplanned timeline that sequences the character's sprite cells, bitmap
states, clips, or procedural assets through the normal adapters.

Resource paths inside an MScript are project-relative, just like
`render.asset` paths after the pack prefix has been included. This keeps old
project scripts and character-owned scripts executable by the same engine.

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

The expression × mouth form is useful for talking faces, but it is not forced
on every character. Patric uses flat cells, Mochi uses paired video clips, and
an irregular atlas can declare source rectangles instead.

## Project copies win

A pack here shadows one bundled inside an installed module, the same
way `modules/` shadows an installed module. Copy the demo in, edit it,
and yours is what plays:

```bash
cp -a ../JaegerAnimation/jaeger_animation/assets/characters/emotes \
      characters/my-emotes
python3 main.py --character my-emotes
```

`Sprite Emotes/` here is a project copy of the demo that ships with
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
