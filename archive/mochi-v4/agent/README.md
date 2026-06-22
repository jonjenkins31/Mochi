# Mochi Agent Node

This node listens for transcribed speech or chat text on the Mochi event bus
and responds with agent replies. The subprocess entrypoint is still
`agent/node.py`, but durable behavior is split into the JROS-style baseline:

- `agent/loop/` — transport-neutral turn logic
- `agent/adapters/` — model/provider backends, currently `ollama` and `mock`
- `agent/tools/` — deterministic agent tools
- `agent/prompts/` and `agent/personas/` — prompt/persona assembly
- `core/safety.py` and `core/memory.py` — safety gates and persistent notes

Animation intent still rides the existing reply topics as structured tags
like `<mode name="happy"/>`; the animation node parses those tags and owns the
actual rendering.

## Running

```bash
python -m agent.node
```

The node expects an Ollama daemon to be available (default:
`http://localhost:11434`). Update `config.yaml` or set environment overrides to
change the model, host, adapter, or timeout.

Alternatively, launch the main Mochi host after setting `enabled: true` for the
`llm` plugin in `config.yaml`, then send text onto the bus:

```bash
python main.py
# then open the chat GUI
python gui/llm_chat_gui.py
```

## Commands

- `node agent model <name>` – switch to a different Ollama model.
- `node agent adapter <mock|ollama>` – switch adapters.
- `node agent system <prompt>` – replace the app system prompt.
- `node agent status` – log the current configuration and message counters.
