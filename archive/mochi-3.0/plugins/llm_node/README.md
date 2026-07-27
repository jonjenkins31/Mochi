# Mochi LLM Node

This node listens for transcribed speech on the Mochi event bus and responds
with locally generated LLM replies using Ollama and the Gemma family of models.

## Running

```bash
python plugins/llm_node/node.py
```

The node expects an Ollama daemon to be available (default:
`http://localhost:11434`). Update `config.yaml` or set environment overrides to
change the model, host, or timeout.

Alternatively, launch the main Mochi host after setting `enabled: true` for the
`llm` plugin in `config.yaml`, then send text onto the bus:

```bash
python main.py
# then open the chat GUI
python gui/llm_chat_gui.py
```

## Commands

- `node llm model <name>` – switch to a different Ollama model.
- `node llm system <prompt>` – replace the system prompt.
- `node llm status` – log the current configuration and message counters.
