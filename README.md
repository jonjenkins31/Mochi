# Mochi Modular Display

Mochi is a modular framework for building LED-style animation pipelines inspired by the Dasai Mochi experience. The host process boots shared infrastructure (a ZeroMQ broker) and one or more plugin processes. Each plugin publishes frames/events and listens for targeted control commands, so features can be added or swapped without touching the core runtime.

## Project Layout

| Path | Role |
| --- | --- |
| `main.py` | Host entry point. Reads `config.yaml`, launches the broker (`core/broker.py`) and configured plugins. |
| `core/` | Shared infrastructure utilities (broker, topic helpers, etc.). |
| `plugins/animation_node/` | The reference animation plugin that renders frames and exposes control commands. |
| `gui/` | Desktop tooling: manual control (`mochi_gui.py`), virtual display, performance monitor, CLI helper. |
| `docs/messaging.md` | Details on address/topic conventions and message payloads. |
| `config.yaml` | Addresses and plugin registry. Add new plugins here by appending to the `plugins:` list. |

## Getting Started

```bash
git clone <repo-url>
cd Mochi
python -m venv .venv
source .venv/bin/activate      # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Run the Host & Plugins

The host script spawns the broker and the default animation node using the addresses found in `config.yaml`.

```bash
python main.py
```

Keep `main.py` running in its own terminal. It will show broker/animation node logs and forward Ctrl+C requests to shut down both processes cleanly.

### Launch Supporting Tools

With the host running you can start any of the GUI helpers from another terminal (with the virtual environment activated):

```bash
# Manual control panel with node overview, mode toggles, color controls, etc.
python gui/mochi_gui.py

# Virtual LED display that subscribes to the frame topic.
python gui/mochi_vdisplay.py

# Console CLI to send quick commands.
python gui/control_cli.py play mscripts/demo_wink.mscript
```

The host monitor caches node health/meta/event messages and is reachable at the `monitor.rep_address` defined in `config.yaml`. For example:

```bash
python - <<'PY'
import zmq
ctx = zmq.Context.instance()
sock = ctx.socket(zmq.REQ)
sock.connect("tcp://127.0.0.1:5560")
sock.send_string("GET health")
print(sock.recv_string())
PY
```

The GUI discovers node health broadcasts automatically. Select a node in the table to send `mode on`, `mode off`, `mode reset`, or size commands. The color picker can target either the active animation (`current`) or the fallback solid color (`solid_color`), which updates the plugin’s stored fallback palette.

### Control Commands

Plugins receive text commands over the ZeroMQ control socket. You can target a specific node explicitly:

```
node animation mode on solid_color
node animation color solid_color 255 0 128
node animation size 64x64
```

Without the `node <id>` prefix, commands go to whichever node the sender is bound to (the bundled GUI defaults to the `animation` node). Responses are emitted as structured event messages on `node.<id>.event`.

For a description of the ZeroMQ addresses and topics, see [docs/messaging.md](docs/messaging.md).

## Developing Plugins

- Place plugin code under `plugins/<your_plugin>/` and provide an entry script similar to `plugins/animation_node/main.py`.
- Use `core.make_node_topics(<node_id>)` to compute your required PUB/SUB topics and call `describe_node_catalog` to publish a `meta` announcement when the plugin starts.
- Emit health metrics (`node.<id>.health`) and event payloads (`node.<id>.event`) to keep tooling in sync.
- Extend `config.yaml` by appending a block to the `plugins:` list. At minimum provide an `id`, `entry`, and `cwd`. Optional `config_key` fields let the host inject a config section into the plugin via `MOCHI_PLUGIN_CONFIG_JSON`.

The existing animation node is a good template: it maintains its own control loop, queues structured events, and publishes frames through the broker so multiple subscribers can consume them without extra wiring.

## Scripts & Animations

- Animation classes live in `plugins/animation_node/animations/` and inherit from the shared `Animation` base. Register a new class in `animations/__init__.py` to expose it as a `mode` command.
- MochiScript files (`plugins/animation_node/mscripts/`) drive scripted sequences. The GUI and CLI can invoke them with `play <path>`; they emit structured commands that flow through the same control interface.

## Contributing

1. Create a branch for your feature or fix.
2. Run `python -m compileall .` or the relevant tests before submitting.
3. Open a pull request describing the change and any new configuration requirements.

## License

See [LICENSE](LICENSE) for details.
