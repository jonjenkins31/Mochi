# Mochi

A virtual character you can run.

> **Jaeger ecosystem identity**
> ID: `org.jenkinsrobotics.app.mochi` · Type: **application** ·
> Role: virtual-character workspace and module host

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
python3 main.py sim                         # no audio hardware
python3 main.py --nodes                     # what runs, and from where
python3 main.py --asset ~/clip.gif          # play any file
python3 main.py --character my-pack         # a specific pack
```

## Bringup variants

`main.py` is the launcher; the manifest is the argument — the same
shape as `ros2 launch <pkg> <file>`.

```
jaeger.toml   the real thing: face, audio driver, voice, hearing
sim.toml      the face alone — no device is opened
```

A variant that changes a **setting** should be a flag. One that
changes **which nodes exist** should not: a flag would have to reach
inside the composition and disable something, where a manifest just
describes a different composition.

`sim` is what you develop against. Opening the microphone takes 3.6s
on macOS, needs a permission grant, and a process killed mid-stream
can wedge CoreAudio until it is restarted — none of which is
interesting while you are working on a character pack or a tab.

## Layout

Same shape as JP01-CC01 — two projects built alike is what makes it a
standard.

```
main.py             JaegerApp(PROJECT_ROOT).run()
jaeger.toml         composition + inline settings for each node
core/               this project's own library code
interfaces/         the GUI — player.py
nodes/              nodes this project owns (JP01 has motor, videorx…)
modules/            imported modules, named by their real providers
characters/         character packs — drop a folder in, it plays
archive/            mochi-3.0 and mochi-v4, kept, never imported
```

Mochi is a workspace, **not a library**. Nothing imports it; you run it
from this directory. That is why `core/` and `interfaces/` can have
generic names — they never enter anyone's site-packages.

## Nothing you work on is hidden

Installed modules are the default and stay out of sight. When you need
to change one, copy it into `modules/` and yours wins — ROS's workspace
overlay, where `~/ws/src` beats `/opt/ros`. Same rule for characters:
`characters/` beats a module's bundled demo.

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

Exporting a pack from Anima Studio into `characters/` is the
whole install step.

## Mochi 3.0 compatibility

All 26 Mochi 3.0 procedural scenes now run through JaegerAnimation,
including the repaired bars, Spotify bitmap, and non-blocking Game of Life
scene. Legacy MScript keyed `EVENT[...]` commands are stateful again.

```bash
python3 main.py --asset assets/math/wave_scene.py
```

## v5.2

The Chat tab talks to a real model. JaegerAgent fills the `mind` slot, and the
whole integration is two messages — `/act/chat` out, `/sense/chat` back — so
no prompt is assembled anywhere in this app and no provider is named outside
`modules/jaeger_agent.py`.

It is deliberately a **chatbot, not an agent**. JaegerAgent ships ~96 tools
that read files and run code; Mochi asks for the bare loop instead
(`JAEGER_AGENT_NO_TOOLS`, set in `main()`), because a desk character wants
conversation and ~96 tool schemas are ~15,000 tokens against a 4096-token
window. Weights load in-process — no server, no account, no API key, nothing
leaving the machine — and `model_path` is left blank in the manifest because
the integration finds a `.gguf` in the usual places. Point it somewhere
specific with `$JAEGER_GGUF`, or swap to LM Studio or Ollama by editing
`[config.mind]` and nothing else.

**Mochi boots as a messaging LLM.** You type, it answers, and no audio device
is opened: `audio_io`, `tts` and `stt` are declared in `jaeger.toml` but not
started, so "off" costs no model load and no recording indicator.

**Power is not routing**, and each node is switchable on its own:

| Question | Where |
|---|---|
| is the STT running? | **Hearing** tab — `Ears` |
| is the TTS running? | **Voice** tab — `Voice` |
| is the camera running? | **Vision** tab — `Eyes` |
| should what it hears be answered by the mind? | **Chat** — `Listen` |
| should the answer be said out loud? | **Chat** — `Speak replies` |

Run the STT to watch transcripts with no voice, or the TTS to audition a
Kokoro voice with no microphone in the room — neither needs the mind. Ticking
a Chat box still starts the node it needs (one click for "I want to talk"),
but turning one off belongs to the tab that owns it. All three tabs read their
switch position back from the supervisor instead of remembering the click,
which is why the same switch appears in two places and they never disagree —
[`core/audio_switch.py`](core/audio_switch.py) is the only thing that moves
them, and it owns the one part that cannot be split: the shared `audio_io`
driver, which must run while either engine does and must capture only while
the ears do.

**The voice loop is a named pipeline, not a pile of knobs.** Testing these
against a real microphone in a real room is what Mochi is for, so Chat has a
pipeline picker, and each entry is a whole composition taken from the
reference scripts in the project root:

| Mode | Shape | Needs |
|---|---|---|
| `assistant` | half duplex — wake phrase (`hey mochi`), mic **paused** while the character talks, 10s follow-up window so a conversation doesn't need the phrase every sentence | nothing extra |
| `chat` | full duplex — no wake phrase, every phrase is a turn, talk over the reply | `pip install speexdsp` for echo cancellation |

Adding a third is a dict in [`core/voice_modes.py`](core/voice_modes.py); every
value in it is a real field of the engine modules' own config, so a mode
composes them rather than reimplementing them.

`assistant` is the default because it needs no echo canceller. `chat` says so
in the log when `speexdsp` is missing rather than quietly feeding the reply
back into the microphone.

**It used to answer itself.** The engine ships three defences against hearing
its own voice and Mochi was calling none of them: `require_wake_word` sat at
its dataclass default of `False`, `self_speech_filter` was on but inert
because nothing ever called `remember_reply()`, and `set_paused()` — the mic
pause the reference script relies on — was never called at all. With a live
mic, no echo canceller and no wake phrase, a reply was transcribed, answered,
and the answer transcribed, forever. All three are wired now: the mode
configures the first two, and [`interfaces/chat.py`](interfaces/chat.py)
drives the pause off `/act/speaker/state`, because it is the only thing that
knows both when the speaker is playing and when a transcript is about to
become a turn.

Which ENGINE runs is the other two tabs' job. **Hearing** lists every
segmentation pipeline the STT module ships — `vad_segment`, `two_pass`,
`continuous`, `phrase_word`, `window`, `local_agreement` — reading its
registry rather than a copied list, and swapping one rebuilds the node,
because the mode is read once when the engine is constructed. **Voice** lists
Kokoro's voices; that one rides each request, so it applies to the next thing
said with no restart, and Chat's spoken replies use the same choice.

The default is `vad_segment`, not the module's own `two_pass`: two_pass
publishes each utterance twice — the fast pass and the accurate re-decode,
both `is_final` — and a chatbot asked the same question twice answers it
twice. It is still in the picker, and worth switching to once the module emits
one final per phrase.

The **Windows** tab restores the standalone interfaces that existed across
Mochi 3.0 and v4. Current-bus versions of the popup player, media player,
virtual display, and performance monitor open in-process. The 19 original
standalone windows remain launchable as isolated visual references until the
later consolidation pass.

The popup player is skinnable again. Its persisted controls live in
`assets/player_settings.yaml`, while every folder under `assets/skins/` can
declare a bezel image and `screen_bbox` in `skin.yaml`. The included TV 1 skin
uses the original Mochi artwork. Open it from **Face → Pop-out player** or
**Windows → Popup player settings**.

The mouth-state axis is what makes it work: hold an expression,
alternate the row, and you have a talking face.

`./setup.sh` installs the framework plus the four current providers — face,
voice, ears, and mind. There is no opt-in flag: a character that shows a face,
speaks, listens, and answers is the current app. Kokoro does pull torch the
first time (~2 GB, a few minutes); after that it is cached and setup takes
seconds.

The `tts`, `stt` and `mind` nodes stay `optional = true` — that is about
RUNTIME, not install. A Pi with no speaker should still boot the face
instead of refusing to start. When a slot is empty, the startup report
and `--nodes` name the package that fills it:

```
  tts          tts         not installed          pip install jaeger-kokoro-tts
```

That package name is an install hint. Runtime module discovery still selects
the installed provider for the slot, while the Interface's Modules tab shows
the exact provider import that was selected.
