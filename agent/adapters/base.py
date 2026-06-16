"""Provider-neutral chat adapter contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ChatTurn:
    role: str
    text: str


class ChatAdapter(Protocol):
    name: str

    def complete(self, *, prompt: str, history: list[ChatTurn]) -> str | None:
        """Return assistant text, or None when the backend cannot answer."""
