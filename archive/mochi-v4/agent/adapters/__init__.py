"""LLM backend adapters."""

from .base import ChatAdapter, ChatTurn
from .ollama import OllamaAdapter, OllamaClient
from .registry import AdapterRegistry, build_adapter_registry

__all__ = [
    "AdapterRegistry",
    "ChatAdapter",
    "ChatTurn",
    "OllamaAdapter",
    "OllamaClient",
    "build_adapter_registry",
]
