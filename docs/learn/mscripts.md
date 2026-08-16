# MochiScript (mscripts)

## What it is

A step-by-step DSL for driving a character: what it shows, what it
says, and what it waits for. Inspired by Fanuc TP motion programs — one
command per line, `COMMAND KEY[value]`, a declared and closed
vocabulary.

```
[Header start]
! what this script is
[Header end]

[Resources start]
K[1]: 'characters/Orbs/orbs.py'
[Resources end]

[Main start]
MATH K[1] STATE[working] COLOR[#6C5CE7] D[1.5]
SAY TXT['This is what I look like while I am thinking.']
[Main end]
```

## Sections

`Header` · `Resources` · `Main` · `Keyframes` · `Track_<name>`

`Keyframes` holds named poses — `P[1]: TOKEN[value] …` — for `MOVE` to
walk between. Same shape as `Resources`, because a keyframe is another
named thing referred to by number.

The list is **closed**. An unknown section is an error in both readers,
and always was — this is not a format where you can invent a heading.

## Two readers, one file

The **engine** (JaegerAnimation) renders: it reads `[Main]` and plays
asset commands, and its job ends at frames on a topic. An app that owns
a voice and a bus **conducts** ([`core/scenes.py`](../../core/scenes.py)):
it reads the same file and also runs the speech and mind commands.

Both understand the whole vocabulary. A script written for one runs on
the other; what the engine cannot do, it skips.

## The vocabulary

### Asset commands — what is on screen

A face is not a thing in this format. A face is a **bitmap**, or a
**sprite**, or an **image**, or a procedural **math** scene, so the
command names what it actually is.

| Command | Plays | Adapter |
|---|---|---|
| `BITMAP K[n]` | a bitmap clip set | `bitmap` |
| `SPRITE K[n]` | a cell from a sprite sheet | `sprite` |
| `IMAGE K[n]` | a still image | `image` |
| `GIF K[n]` | an animated gif | `gif` |
| `VIDEO K[n]` | a video file | `video` |
| `MEDIA K[n]` | any of the above, by extension | chosen |
| `MATH K[n]` | a procedural Python scene | `math` |

`K[n]` is a resource declared in `[Resources]`. `D[seconds]` holds the
step. **Every other token is passed straight through to the adapter**,
which is how a script sets things this format never had to learn:

```
MATH K[1] STATE[searching] COLOR[#4FC3F7] SIZE[20] SPD[2.0] D[2.0]
```

`STATE`, `COLOR`, `SIZE` and `SPD` are the *Orbs* scene's parameters —
`characters/Orbs/orbs.py` reads them, nothing else does. A different
math scene declares different ones. Common tokens across the media
commands: `FIT`, `LOOP`, `SPD`, `BG`, `FG`, `SRC`.

**A clip command is a complete instruction.** Each one opens a new
clip, so a line carrying only `COLOR` loses the state — repeat the
tokens you want kept.

### Motion — waypoints between poses

A robot program does not list every position it passes through. It
names the ones that matter and says how to get between them, and
`MOVE` is that for a math scene's parameters.

```
[Keyframes start]
P[1]: STATE[idle] GAZE[0,0]     TILT[0]
P[2]: STATE[idle] GAZE[-0.85,0] TILT[-14]
P[3]: STATE[idle] GAZE[0.85,0]  TILT[14]
[Keyframes end]

[Main start]
MOVE K[1] PATH[1,2,3] D[6.0] EASE[smooth]
[Main end]
```

| Token | Means |
|---|---|
| `PATH[1,2,3]` | the waypoints, in order. Repeat one to return to it |
| `D[s]` | how long the whole move takes |
| `EASE[…]` | `fine` / `linear` stop dead on each point; `smooth` / `cnt` round the corner; also `in`, `out` |

Numbers, `#RRGGBB` colours and `x,y` pairs **interpolate**. Anything
else is a word — `STATE[alert]`, `LAYERS[bezel,pupil]` — and half of a
word is nothing, so it changes at the midpoint.

**The scene walks the path, not the conductor.** No topic can update a
clip once it is running, so the whole path rides in the clip's params
and is stepped against the clip's own clock — at frame rate, rather
than at whatever rate a script could republish. A scene opts in by
calling `core.tween.path_from()` in `on_enter`; one that does not just
sits on the first waypoint.

### Character commands

| Command | Does |
|---|---|
| `FACE EXPR[name] D[s]` | show an expression **by name**, resolved through `character.yaml` |

The one command that is not about an asset. `FACE EXPR[happy]` works on
any pack that declares `happy`, without the script knowing whether that
is a bitmap or a video. Use it for portable scripts; use the asset
commands when you want exact control.

### Voice, ears and mind

These are the conductor's — the engine skips them.

| Command | Module | Does |
|---|---|---|
| `SAY TXT['...']` | **TTS** | speak a line, and **wait for it to finish** |
| `LISTEN D[s]` | **STT** | hold until a person answers, or time out |
| `ASK D[s]` | **LLM** | hand what was just heard to the mind, and speak the answer |

`SAY` blocks on the done-ack rather than guessing at a duration, so a
script stays in step with a voice that is slower than expected. With no
voice module running it holds a word-count estimate instead, so the
performance still reads as one.

`ASK` is the one step whose words are **not written down**. Everything
else in a script is authored; this hands the turn to the model and
carries on afterwards.

### Control flow

| Command | Does |
|---|---|
| `LBL[n]` | a label. `LBL[1:name]` — the name is a comment |
| `JMP LBL[n]` | jump to it |

Both readers cap jumps per frame, so a loop with nothing timed in it
cannot hang the display.

## Where it lives

| Part | Where |
|---|---|
| Engine reference | JaegerAnimation `jaeger_animation/docs/MSCRIPT.md` |
| Interpreter (`[Main]`, asset commands) | JaegerAnimation `procedural/mscript_engine.py` |
| Command → adapter binding | JaegerAnimation `adapters/mscript_adapter.py` |
| Conductor (`SAY`/`LISTEN`/`ASK` + clips) | Mochi [`core/scenes.py`](../../core/scenes.py) |
| Waypoint interpolation (`MOVE`) | Mochi [`core/tween.py`](../../core/tween.py) |
| Track compiler (`[Track_*]` → Timeline) | Mochi [`core/staging.py`](../../core/staging.py) |
| Editor (text + nodes) | Mochi [`interfaces/mscript_editor.py`](../../interfaces/mscript_editor.py) |
| Runner | Mochi [`interfaces/scripts.py`](../../interfaces/scripts.py) — the **Scripts** tab |
| Character scripts | `characters/<id>/mscripts/*.mscript` |
| Engine demo scripts | `assets/mscripts/*.mscript` |

## Try it

Open the **Scripts** tab, pick `tour`, press Run. It is Orbs walking
through all nine of its shapes, then its colours, then both sizes and
the speed knob — talking the whole way. Every parameter it demonstrates
is a token in
[`characters/Orbs/mscripts/tour.mscript`](../../characters/Orbs/mscripts/tour.mscript),
which is the point of it: anything you can see, you can write down.

`characters/bitmap man/mscripts/` has the simpler ones —
`blink.mscript` is pure animation, `knock_knock.mscript` uses `LISTEN`.

## History

- Mochi-specific, inspired by Fanuc robotics motion programs.
- `LBL` / `JMP` were specified in v2.0 and implemented in the engine on
  2026-08-09. Scripts written before then still run identically.
- `[Keyframes]` was declared from the start and unimplemented until
  2026-08-15, when `MOVE` gave it something to hold.
- The conductor learned the **asset commands** on 2026-08-15. Before
  that it only understood `FACE`, so a script that was pure animation
  could not be run as a performance — and "face" was the wrong word for
  it anyway, since a face is a sprite or an image or a math scene.

## What's coming

`dev/docs/future_multi_timeline.md` captures the intent to split
mscripts: a general multi-channel timeline in a future format, with
mscript scoped to the channel DSL where its Fanuc-style strengths
belong. A follow-up project, not current scope.
