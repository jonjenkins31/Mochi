"""Runtime registry for LLM/chat adapters."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from .base import ChatAdapter
from .mock import MockAdapter
from .ollama import OllamaAdapter


@dataclass
class AdapterRegistry:
    adapters: dict[str, ChatAdapter]
    active: str

    def get(self) -> ChatAdapter:
        return self.adapters[self.active]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.adapters))

    def use(self, name: str) -> bool:
        if name not in self.adapters:
            return False
        self.active = name
        return True


def build_adapter_registry(
    *,
    active: str = "ollama",
    ollama_host: str = "http://localhost:11434",
    ollama_model: str = "gemma3:12b",
    ollama_timeout: float = 30.0,
    logger: Logger | None = None,
) -> AdapterRegistry:
    adapters: dict[str, ChatAdapter] = {
        "mock": MockAdapter(),
        "ollama": OllamaAdapter(
            base_url=ollama_host,
            model=ollama_model,
            timeout=ollama_timeout,
            logger=logger,
        ),
    }
    return AdapterRegistry(
        adapters=adapters,
        active=active if active in adapters else "ollama",
    )
