# Mochi — animated character companion

> A modular ZeroMQ-bus-driven framework for building animated
> character displays.  Inspired by the Dasai Mochi3 desktop toy,
> reimagined as an open, extensible platform for animation
> education, character packs, and operator-driven performance.

Part of the **Jenkins Robotics** open-source robotics + AI stack.

---

## Built by Jenkins Robotics

Mochi is one piece of the larger Jenkins Robotics ecosystem —
home robotics, voice AI companions, animated avatars, and
educational hands-on robotics + animation.

### Follow + support the project

- **YouTube:** subscribe for build logs, animation tutorials,
  Mochi authoring workflows, and JROS (Jenkins Robot Operating
  System) development streams →
  [youtube.com/@Jenkins_Robotics](https://www.youtube.com/@Jenkins_Robotics)
- **Patreon:** if Mochi or any of the Jenkins Robotics projects
  are useful to you, becoming a patron directly funds open
  development + new tutorials →
  [patreon.com/JenkinsRobotics](https://www.patreon.com/JenkinsRobotics)
- **GitHub:** the rest of the stack (JROS, VoiceLLM, AgenticLLM,
  Hermes, JP01 robot firmware) lives at
  [github.com/jonathanjenkins](https://github.com/jonathanjenkins)

Like, subscribe, share — every signal helps justify the time
that goes into shipping these projects publicly.

---

## What Mochi does

- **Renders animations** of every common type on a small virtual
  display: PNG / bitmap / GIF / sprite / video / procedural
  (Python) / declarative JSON / scripted (MochiScript)
- **Companion app** (Wondershare-style Qt UI) for browsing 167+
  catalogued animations, picking character packs, configuring
  scenes + triggers, and teaching others about animation
  techniques
- **Frameless mini window** that floats on your desktop with
  customisable body skins (CRT bezel, JDM dash, whatever you
  author)
- **ZeroMQ bus** between the renderer node, agent node, and
  companion app — so the same architecture scales from "single
  app on my desk" to "distributed across multiple machines"

## Quick start

```bash
git clone https://github.com/jonathanjenkins/Mochi.git
cd Mochi
python3 -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Boot the broker + animation node + LLM node + legacy Tk GUI
python main.py

# In a separate terminal — open the new Wondershare-style companion
python gui/mochi_companion.py
```

In the companion app's top toolbar, click **Open Mini Window** to
spawn the frameless TV-bezel overlay.  Click any animation in the
**Library** tab to fire it.

## What's inside

### Top-level layout

| Path | Role |
| --- | --- |
| `main.py` | Host entry point.  Reads `config.yaml`, launches the broker (`transport/broker.py`) + each enabled plugin. |
| `agent/` | The cognitive node (LLM brain — picks animations from context). |
| `nodes/` | Peripheral nodes — `nodes/animation/` is the renderer with 7 backend types. |
| `transport/` | The ZeroMQ bus + topics + message envelopes + base-node class. |
| `core/` | Shared infrastructure (host monitor + plugin registry). |
| `gui/` | Desktop tooling — companion app, mini window overlay, legacy Tk control panel, perf monitor, CLI helper. |
| `tools/` | Content editors (sprite / bitmap / mscript) + catalog/prompt generators. |
| `assets/` | Animations + skins + packs + generated catalogs. |
| `docs/` | Architectural docs + the Learn tab content. |

### Companion app (`gui/mochi_companion.py`)

Wondershare-inspired Qt UI with 9 sidebar surfaces.  As of
mochi-v4 / `SUPERSEDE_TK_PLAN.md` Phase 6, it absorbed every
feature of the legacy Tk debug panel:

| Tab | What's there |
| --- | --- |
| **Home** | Operator dashboard — active animation hero card, recent strip, Active-nodes table (with per-node Stop + Reset), Open Perf Monitor button. |
| **Library** | 4-col card grid of all catalogued animations.  Three filter dimensions (Mood / Type / Curation) + search.  Click → fires via the bus. |
| **Packs** | Pack browser — empty state → grid → slot detail view → Set Active. |
| **Scenes / Triggers / Schedule** | Stubs (Phase B + C of the original plan). |
| **Editors** | Tiles for Sprite / Bitmap / MochiScript editors + Mochi Studio.  Click "Open" to launch as subprocess. |
| **Learn** | 9-chapter markdown viewer covering every animation type Mochi supports. |
| **Settings** | Skin picker + advanced toggle revealing Renderer (color picker + canvas size + reset) and Diagnostics (raw command + quit node). |

**Top toolbar:**
- Live status pill (animation node mode / size / fps / mem)
- Stop button (deactivates the current animation)
- Community shortcuts (▶ YouTube · ♥ Patreon · ◯ Discord · ? Help)
- Open Mini Window button (frameless Qt overlay with active skin)

**Sidebar bottom:** Jenkins Robotics promo card with YouTube + Patreon CTAs.

### Animation types Mochi can render

| Type | Count today | Adapter file |
| --- | --- | --- |
| GIFs | 68 | `nodes/animation/animations/gif_handler.py` |
| Video | 31 | `nodes/animation/animations/video_handler.py` |
| Math (procedural Python) | 26 | `nodes/animation/animations/math_handler.py` |
| MochiScript | 18 | `nodes/animation/plugin_core/mscript_engine.py` |
| Eye animations (JSON) | 6 | `nodes/animation/animations/__init__.py` |
| PNG | 6 | `nodes/animation/animations/image_handler.py` |
| Bitmaps (1-bit) | 5 | `nodes/animation/animations/bitmap_handler.py` |
| Icons | 4 | `nodes/animation/animations/image_handler.py` |
| BMP (raw) | 2 | `nodes/animation/animations/bitmap_handler.py` |
| Procedural | 1 | `nodes/animation/animations/math_handler.py` |

Each type has its own chapter under
[`docs/learn/`](docs/learn/index.md) explaining the history,
how it works, and how Mochi renders it.

## Project docs

| Doc | What it covers |
| --- | --- |
| [`docs/OPERATOR_PRODUCT_PLAN.md`](docs/OPERATOR_PRODUCT_PLAN.md) | Comparable-product research (Dasai Mochi3, EMO, Vector, Eilik, VTube Studio, Divoom, Shimeji) + phased build plan. |
| [`docs/PACK_CONVENTION.md`](docs/PACK_CONVENTION.md) | How character/style packs are authored (`assets/packs/<id>/pack.yaml`). |
| [`docs/SKIN_CONVENTION.md`](docs/SKIN_CONVENTION.md) | How body / bezel skins are authored (`assets/skins/<id>/`). |
| [`docs/ANIMATION_REVIEW.md`](docs/ANIMATION_REVIEW.md) | The LLM-track review (animation-aware system prompt + bridge). |
| [`docs/future_multi_timeline.md`](docs/future_multi_timeline.md) | The multi-channel timeline idea (split mscript into general timeline + motor DSL). |
| [`docs/messaging.md`](docs/messaging.md) | ZeroMQ addresses + topic conventions + message payloads. |
| [`docs/learn/index.md`](docs/learn/index.md) | The Learn tab content — animation history + per-type explainers. |

## Authoring content

### Add a new animation

Drop the file under `assets/<type>/` (matching one of the
supported types).  Run `python tools/build_catalog.py`.  The
animation appears in the companion's Library on next refresh.

### Author a character pack

See [`docs/PACK_CONVENTION.md`](docs/PACK_CONVENTION.md).  Short
version:

```
assets/packs/<your_id>/
├── pack.yaml          # required: schema + slot map
├── idle.gif           # named slot files (operator picks slot names)
├── happy.gif
├── ...
└── README.md          # optional
```

The pack auto-appears on the companion's Packs tab.

### Author a skin (body / bezel)

See [`docs/SKIN_CONVENTION.md`](docs/SKIN_CONVENTION.md).

```
assets/skins/<your_id>/
├── body.png           # required: alpha-cutout body image
├── meta.yaml          # required: screen_bbox + window defaults
└── README.md          # optional
```

The skin auto-appears in the companion's Settings.

## Host monitor + control

The host monitor caches node health/meta/event messages.  Reach
it at `monitor.rep_address` from `config.yaml`:

```bash
python tools/monitor_cli.py --pretty GET health
```

Or send raw ZMQ commands to the animation node's ctrl socket:

```bash
python gui/control_cli.py "node animation mode on solid_color"
python gui/control_cli.py "node animation color solid_color 255 0 128"
python gui/control_cli.py "node animation size 64x64"
```

## Developing nodes

- Place node code under `nodes/<your_node>/` and provide an entry
  script following the pattern in `nodes/animation/node.py`
- Use `transport.make_node_topics(<node_id>)` for the PUB/SUB
  topic helpers; call `describe_node_catalog` to publish a `meta`
  announcement at startup
- Emit health metrics (`node.<id>.health`) + structured event
  payloads (`node.<id>.event`) so tooling stays in sync
- Drop a `config.yaml` next to your `node.py` declaring transport
  addresses, defaults, and a `capabilities` block for GUI metadata
- Append a block to the root `config.yaml`'s `plugins:` list with
  `id`, `module` (or `entry`), `cwd`, and `config_path`

The existing animation node is the canonical template — it
maintains its own control loop, queues structured events,
publishes frames through the broker so multiple subscribers can
consume them without additional wiring.

## Companion projects in the Jenkins Robotics stack

- **[JROS](https://github.com/jonathanjenkins/JROS)** — Jenkins
  Robot Operating System.  The full undertaking: agent + voice +
  vision + animation + motor.  Mochi is the structural pattern
  testbed for JROS's animation pipeline.
- **[VoiceLLM](https://github.com/jonathanjenkins/VoiceLLM)** —
  standalone voice agent (Eve) — STT + LLM + TTS.  Lessons fed
  back into JROS.
- **[AgenticLLM / python_jaeger](https://github.com/jonathanjenkins/AgenticLLM)** —
  standalone tool-using LLM agent.  Lessons fed back into JROS.
- **JP01 firmware** — the hardware side: ESP32 robot controllers
  + LED matrix display drivers.

## Contributing

1. Branch from `main`
2. Run `python -m compileall .` plus any relevant smoke tests
3. Open a PR describing the change + any new config requirements

## License

See [LICENSE](LICENSE).

---

### Stay connected

If you got this far, you probably care about open-source
robotics + animation + AI.  The Jenkins Robotics YouTube channel
+ Patreon are the best ways to follow new work AND help fund it:

- **YouTube:** [youtube.com/@Jenkins_Robotics](https://www.youtube.com/@Jenkins_Robotics)
- **Patreon:** [patreon.com/JenkinsRobotics](https://www.patreon.com/JenkinsRobotics)

Thanks for reading.
