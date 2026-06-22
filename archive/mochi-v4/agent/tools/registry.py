"""Mochi agent tools.

Tools return normal assistant text. Animation intent travels through the
existing reply channel as structured tags, which the animation node already
parses and dispatches.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any, Callable


@dataclasses.dataclass
class Tool:
    name: str
    description: str
    pattern: re.Pattern
    fn: Callable[[dict[str, str]], str]


_MOOD_TO_MODE = {
    "happy": "happy",
    "sad": "sad",
    "angry": "angry",
    "curious": "curious",
    "calm": "calm",
    "off": "",
}


def build_tools(runtime: Any) -> list[Tool]:
    def mood(args: dict[str, str]) -> str:
        emotion = args["emotion"].lower()
        mode = _MOOD_TO_MODE[emotion]
        if not mode:
            return "Going quiet. <stop/>"
        return f"I feel {emotion}. <mode name=\"{mode}\"/>"

    def remember(args: dict[str, str]) -> str:
        note = args["note"].strip()
        runtime.memory.remember(note)
        return f"Remembered: {note}"

    def recall(args: dict[str, str]) -> str:  # noqa: ARG001
        notes = runtime.memory.recall()
        if not notes:
            return "Nothing remembered yet."
        return "I remember:\n" + "\n".join(f"- {note}" for note in notes)

    def forget(args: dict[str, str]) -> str:  # noqa: ARG001
        runtime.memory.clear()
        return "Memory cleared."

    def adapter_status(args: dict[str, str]) -> str:  # noqa: ARG001
        return (
            f"Active adapter: {runtime.adapters.active}. "
            f"Available: {', '.join(runtime.adapters.names())}."
        )

    def use_adapter(args: dict[str, str]) -> str:
        name = args["name"].lower()
        if not runtime.adapters.use(name):
            return (
                f"Unknown adapter '{name}'. Available: "
                f"{', '.join(runtime.adapters.names())}."
            )
        return f"Using adapter: {name}."

    return [
        Tool(
            "mood",
            "happy|sad|angry|curious|calm|off",
            re.compile(
                r"\b(?P<emotion>happy|sad|angry|curious|calm|off)\b",
                re.I,
            ),
            mood,
        ),
        Tool("memory.remember", "remember <note>",
             re.compile(r"\bremember\s+(?P<note>.+)$", re.I), remember),
        Tool("memory.recall", "recall",
             re.compile(r"\brecall\b", re.I), recall),
        Tool("memory.forget", "forget everything force",
             re.compile(r"\bforget\s+everything\b", re.I), forget),
        Tool("adapter.status", "adapter",
             re.compile(r"^\s*adapter\s*$", re.I), adapter_status),
        Tool("adapter.use", "use adapter mock|ollama",
             re.compile(r"\buse\s+adapter\s+(?P<name>\w+)\b", re.I),
             use_adapter),
    ]


def match_tool(tools: list[Tool],
               text: str) -> tuple[Tool | None, dict[str, str]]:
    for tool in tools:
        match = tool.pattern.search(text)
        if match:
            return tool, match.groupdict()
    return None, {}
