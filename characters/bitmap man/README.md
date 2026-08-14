# Bitmap Man — the control testbed

Two monochrome eyes on a 32×32 grid, six expressions, no mouth. The
simplest character in the project, and that is why the control work is
demonstrated here: if a control layer needs a rich character to look
like a performance, it is doing work the art should be doing.

```
neutral   happy   closed   look_up   look_down   sad
```

## The demos, in the order they get harder

Each one proves something the previous could not express.

| # | Demo | File | Proves |
|---|------|------|--------|
| 1 | **idle** | `mscripts/idle.mscript` | a loop — `LBL`/`JMP`, no timing to get right |
| 2 | **looking around** | `mscripts/looking_around.mscript` | face + voice, sequenced. `SAY` waits for the done-ack so lines never overlap |
| 3 | **knock knock** | `mscripts/knock_knock.mscript` | `LISTEN` — the script **stops** until a person answers, twice |
| 4 | **telling a secret** | `../../assets/timelines/bitmap_secret.json` | **simultaneity** — the eyes check the room *while* a line is spoken |
| 5 | **two cues** | `../../assets/timelines/bitmap_two_cues.json` | two mscripts running **concurrently** on one clock, beside a voice track |
| 6 | **improv** | `mscripts/improv.mscript` | `ASK` — the author writes the turns, the **mind** writes the words |
| — | *blink* | `mscripts/blink.mscript` | animation only; the engine's to play, not a performance |
| — | *glance about* | `mscripts/glance_about.mscript` | a looping cue, meant to run **on a track** beside a voice |

Run 1, 2, 3 and 6 from **Stage → Performances**; 4 and 5 from
**Stage → Scenes**. Everything is data — the MScript Editor opens the
scripts and the node graph draws them.

## Which shape to reach for

|  | performance (`.mscript`) | scene (`.json` timeline) |
|---|---|---|
| Shape | program counter | tracks on one clock |
| Good at | order, branching, **waiting** | **simultaneity** |
| Can stop for a person | yes (`LISTEN`) | no |
| Analogy | a MIDI pattern | the arrangement |

They compose: a timeline track of kind `script` holds an mscript as a
**cue**, so channels come from tracks and order comes from the cue. That
is demo 5.

## Commands

```
FACE EXPR[happy] D[1.5]     the character's own vocabulary
SAY  TXT['...']             speak, and wait for /act/speech/spoken
WAIT D[0.4]
LISTEN D[10]                hold until a person answers
ASK  D[25]                  hand the last thing heard to the mind
LBL[1:name] / JMP LBL[1]    loop
```

`ASK` needs **no tools**. A reply is text, and text is all a chat model
returns — the character's expression vocabulary is taught in one line of
prompt, and a leading `[happy]` marker in the reply is applied and
stripped before synthesis. Measured against gemma-4-E4B with
`JAEGER_AGENT_NO_TOOLS=1`:

```
you   "Look up at the ceiling for me."
raw   "[look_up] Ceiling."
```

251 characters of prompt, against ~3,600 **tokens** for even a scoped
tool catalogue.

## Known limits

- A cue that `LISTEN`s stops for a person; a wall clock does not stop
  with it. On a timeline the other tracks carry on and sync is lost
  after. Choosing per cue — hold the transport, or let it drift — is
  not built.
- mscript has no registers, comparisons or arithmetic yet, so `JMP` is
  unconditional. `IF R[1] > 3 JMP LBL[2]` is the next step.
- `ASK` blocks for as long as inference takes. Fine on its own thread,
  wrong inside a timeline that owes 30 fps — a resolved-ahead track is
  the answer there, not a blocking call at the playhead.
