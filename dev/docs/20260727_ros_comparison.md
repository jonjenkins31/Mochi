# Mochi v5 vs. the same app built on ROS 2

Written 2026-07-27 against the shipped v5.0 tree. The question: if you
built this exact app — a window that plays a character pack and any
media file you hand it — on ROS 2 instead, what would differ?

Not "which is better." Where the two frameworks make you do different
work, and which of those differences are real.

---

## What Mochi v5.0 actually is

```
main.py                140   flags → JaegerApp(PROJECT_ROOT).run()
jaeger.toml             74   the composition
config.yaml             18   settings
core/characters.py     209   reading a character pack
interfaces/player.py   335   the window
                       ───
                       776   of which 168 lines are comment or blank
```

Roughly **600 lines of code**, and none of it is transport, lifecycle,
process supervision, or image decoding. Those come from the framework
and one installed module.

---

## Where the two are the same

More than the names suggest. The mapping is close enough that a ROS
engineer reads this app in minutes:

| ROS 2 | JaegerOS | Same idea? |
|---|---|---|
| package + `package.xml` | module + `module.yaml` | yes |
| node | node | yes |
| launch file | `jaeger.toml` | yes, see below |
| params YAML | `config.yaml` | yes |
| `.msg` + topics | msgspec structs + topics | yes |
| `ros2 node list` / `topic info` | control plane verbs | yes |
| managed-node lifecycle | `setup/tick/teardown/health` | yes |
| `~/ws/src` overlays `/opt/ros` | `modules/` shadows installed | yes |
| QoS profiles | per-topic `Qos(depth, reliability)` | ours is smaller |

The overlay in particular was borrowed on purpose after the operator
asked "is this how coding works in ROS?" — it wasn't there, and it
should have been.

---

## Five real differences

### 1. Launch is data, not a program

A ROS launch file is Python that **executes**:

```python
def generate_launch_description():
    return LaunchDescription([
        Node(package="mochi_face", executable="animation_node",
             parameters=[{"width": 256}]),
    ])
```

`jaeger.toml` is data that gets **read**:

```toml
[[node]]
id = "animation"
slot = "animation"
config_key = "animation"
```

The cost is real: no conditionals, no loops, no computed topic names.
ROS launch can spawn N nodes from a list comprehension; this cannot.

What it buys is that `--nodes` can print the whole composition without
running any of it, and a malformed manifest is a parse error naming
the field rather than a traceback. For an app this size that trade is
clearly right. For a 40-node robot it might not be.

### 2. Binding by capability, not by executable

ROS launch names the thing to run: package `mochi_face`, executable
`animation_node`. Swapping engines means editing the launch file.

`slot = "animation"` names **what the app needs**, and whichever
installed module claims that slot fills it. Mochi's manifest never
says `jaeger_animation` — only `requirements.txt` does.

ROS's nearest equivalent is `pluginlib`, which swaps implementations
*inside* a node via a C++ class loader. Ours swaps at composition, in
the same file that declares the node. That is genuinely simpler, and
it is why the overlay works: drop a module into `modules/` and it
takes the slot with no edit anywhere.

**Honest caveat:** with one module per slot installed, this has never
been stressed. Two animation modules would need a tiebreak the
manifest cannot currently express.

### 3. One process by default, many by declaration

ROS 2 nodes are separate processes talking over DDS. Sharing a process
requires composable nodes and an explicit container.

Here `backend = "inproc"` is the default and a topic hand-off is a
reference pass — measured earlier today at **0.011 ms**, against a
10 ms audio frame. `backend = "zmq"` moves the same nodes into
separate processes with no code change.

For a desktop character player, in-process is obviously right and ROS
would have you paying DDS serialisation to move pixels between two
things in the same window. For a distributed robot, DDS's discovery and
multicast are things we do not have and would have to build.

### 4. No build step

ROS: `colcon build`, source the overlay, then run. A Python-only ROS
package still needs `setup.py`, an `install/` tree, and a re-source
after changes.

Here: `python3 main.py`. The project is not installed at all — it is a
workspace on `sys.path`, which is why `core/` and `interfaces/` can
have generic names.

This is mostly a consequence of being Python-only. ROS pays that cost
because it has to link C++.

### 5. Agentic I/O has no ROS equivalent

`module.yaml` declares a `tools:` surface alongside its topics — the
same capability shaped for a language model rather than for another
node. ROS has services and actions; both are for programs.

Not exercised in v5.0, which has no mind. It is the reason v5.1 is
three manifest lines rather than an integration project.

---

## The same app, on ROS 2

Sketching it honestly:

```
mochi_ws/src/
  mochi_face/            package.xml, setup.py
    animation_node.py    subscribes /act/display/play, publishes frames
    msg/DisplayFrame.msg
  mochi_player/          package.xml, setup.py
    player_node.py       Qt window, subscribes frames
    launch/mochi.launch.py
    config/params.yaml
```

**What ROS gives you that we do not:**

- `rqt_graph`, `ros2 bag`, `rviz` — mature tooling we have thin
  equivalents of at best. `ros2 bag record` alone is worth a lot.
- Real distribution. DDS discovery means a node on another machine
  joins by existing. Our zmq backend needs endpoints configured.
- A decade of people having hit the problems first.

**What it would cost:**

- `DisplayFrame.msg` + `DisplayCommand.msg` + a build step to generate
  them, versus a msgspec struct in a file.
- The player and the engine as separate processes, so every frame is
  serialised and copied — for two things drawing in one window.
- Qt-in-a-ROS-node is a known awkwardness: you either spin the ROS
  executor in a thread and marshal to the Qt loop, or use a Qt-aware
  executor. We hit the same problem and solved it the same way — the
  bus callback stashes a `QImage`, a `QTimer` paints it.
- No character-pack concept. That is app-tier either way, so
  `characters.py` would exist unchanged.

**Rough size:** the ROS version is maybe 1.3–1.6× the code, mostly
`package.xml`/`setup.py` boilerplate and message definitions, plus the
executor/Qt bridge. Not dramatically bigger. The bigger difference is
that `colcon build` sits between every edit and seeing it.

---

## What we would take from ROS if we took one thing

**`ros2 bag`.** Record every message on the bus, replay it later. It
turns "the face glitched once" into a file you can hand someone. We
have a control plane that can inspect a live system and nothing that
can record one.

Second would be `rqt_graph` — `--nodes` prints the composition, but a
picture of who actually publishes to whom, from live traffic rather
than from manifests, is a different and better thing.

---

## The honest summary

For **this** app, the JaegerOS version is smaller and more direct,
mostly because it skips a build step and a process boundary that ROS
would insist on for no benefit at a desktop character player's scale.

For a **twelve-node robot with three machines**, most of that advantage
inverts: DDS discovery, `ros2 bag`, and rviz are load-bearing, and a
declarative launch file with no loops starts to chafe.

Which is roughly the shape the ecosystem already assumes — Mochi is an
app, JP01 is a body, and the second one is where the framework has the
most left to prove.

---

## Appendix: the two root directories, side by side

The question that prompted this section: *what would the root look
like in ROS?*

### Mochi v5 today

```
Mochi/                          ← you run from here
  main.py                       python3 main.py
  jaeger.toml                   the composition
  config.yaml                   settings
  requirements.txt
  setup.sh
  core/                         this project's library code
    characters.py
  interfaces/                   the GUI
    player.py
  nodes/                        node code this project owns (empty)
  modules/                      project modules — shadow installed ones
  assets/characters/emotes/     packs
  dev/                          tests, docs, reference
  docs/                         the published site
  archive/                      3.0 and v4
```

Fifteen entries, all source. Nothing generated.

### The same app as a ROS 2 workspace

```
mochi_ws/                       ← you run from here
  src/                          ← ALL source lives one level down
    mochi_msgs/                 messages need their OWN package
      package.xml
      CMakeLists.txt            ...and CMake, even for a Python app
      msg/
        DisplayCommand.msg
        DisplayFrame.msg
        DisplayState.msg
    mochi_face/                 the animation engine
      package.xml
      setup.py
      setup.cfg
      resource/mochi_face       empty marker file, required
      mochi_face/
        __init__.py
        animation_node.py
        adapters/
    mochi_player/               the app
      package.xml
      setup.py
      setup.cfg
      resource/mochi_player
      mochi_player/
        __init__.py
        player_node.py
        characters.py
      launch/mochi.launch.py
      config/params.yaml
      assets/characters/emotes/
  build/                        ← generated by colcon, gitignored
  install/                      ← generated, and what you source
  log/                          ← generated
```

### What the difference actually is

**Source moves down a level.** ROS reserves the workspace root for
`src/` plus three generated directories. `cd mochi_ws` then
`cd src/mochi_player` to reach what Mochi keeps at the top. That is
the price of a workspace holding *many* packages — and this app is one
package plus a shared message package.

**Four files per package before any code.** `package.xml`, `setup.py`,
`setup.cfg`, and an empty `resource/<name>` marker. Miss the marker
and the package builds but does not appear to `ros2 run`, which is a
memorable afternoon.

**Messages need CMake.** `rosidl_generate_interfaces` only runs under
`ament_cmake`, so a pure-Python project still carries one CMake
package purely to generate three message types. Mochi's equivalent is
a msgspec struct in `topics.py` — no package, no build.

**Three generated directories to ignore.** `build/`, `install/`,
`log/`. You must `source install/setup.bash` after every build, and
forgetting is the single most common ROS confusion: your change ran,
nothing happened, because the old copy is still installed.

**Where the character pack goes is the same problem either way.** It
is app data, so it lands in `mochi_player/assets/` and gets declared
in `setup.py`'s `data_files` so `colcon` copies it into `install/`.
Mochi reads it from the source tree directly, which is simpler right
up until you package for distribution.

### The honest read

For **one app**, ROS's layout is mostly overhead: `src/` exists to
hold packages you do not have, and four boilerplate files per package
buy nothing at this size.

For **twelve packages across three machines**, it stops being
overhead. `src/` is where you clone other people's work, `install/`
is the overlay that makes versioning tractable, and the build step is
what lets C++ and Python packages coexist.

Mochi is the first case. JP01 is closer to the second, and it is worth
watching whether a flat project root still reads well when a body has
a dozen nodes and vendored drivers.
