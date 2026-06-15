"""LLM backend adapters — one module per provider.

Each adapter exposes a client class consumable by agent/node.py.
Today: ollama only. Future backends slot in alongside.
"""

from .ollama import OllamaClient  # noqa: F401
