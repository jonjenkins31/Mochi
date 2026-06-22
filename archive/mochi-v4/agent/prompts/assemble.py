"""Prompt assembly for Mochi's agent."""

from __future__ import annotations

from typing import Any

from agent.personas.mochi import SYSTEM


def build_prompt(
    *,
    persona: str,
    system_prompt: str,
    memories: list[str],
    tools: list[Any],
) -> str:
    memory_block = "\n".join(f"- {m}" for m in memories) or "- none"
    tool_block = "\n".join(f"- {t.name}: {t.description}" for t in tools)
    return (
        f"Persona: {persona}\n"
        f"{SYSTEM}\n\n"
        f"App system prompt:\n{system_prompt or '(none)'}\n\n"
        f"Memory:\n{memory_block}\n\n"
        f"Tools:\n{tool_block}"
    )
