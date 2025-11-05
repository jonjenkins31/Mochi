# Mochi Node Template

This directory provides a lightweight scaffold for implementing new Mochi
plugin nodes. Copy the folder, rename it, and tailor the contents for your
feature.

Key files:

- `config.yaml` – starter configuration with the standard node settings.
- `bootstrap.py` – helpers for loading configuration, configuring logging, and
  handling optional topics.
- `node.py` – contains both the example `TemplateNode` implementation and the
  entry point that wires configuration into it.

New nodes typically:

1. Copy this directory to `plugins/<your_node_name>/`.
2. Replace `TemplateNode` with your implementation.
3. Update `config.yaml` defaults.
4. Update `node.py` with your entry‐point logic (or replace it entirely).
