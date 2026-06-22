"""Deterministic local adapter for tests and offline development."""

from __future__ import annotations

from .base import ChatTurn


class MockAdapter:
    name = "mock"

    def complete(self, *, prompt: str, history: list[ChatTurn]) -> str | None:
        last = history[-1].text if history else ""
        lowered = last.lower()
        if "hi" in lowered or "hello" in lowered:
            return "Hello. <mode name=\"happy\"/>"
        return f"I heard: {last}"
