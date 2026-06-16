"""Toolkit- and transport-neutral Mochi agent turn logic."""

from __future__ import annotations

import datetime as dt

from agent.adapters.base import ChatTurn
from agent.adapters.registry import AdapterRegistry
from agent.prompts.assemble import build_prompt
from agent.tools.registry import build_tools, match_tool
from core.memory import Memory
from core.safety import check_command


class AgentRuntime:
    def __init__(
        self,
        *,
        adapters: AdapterRegistry,
        persona: str = "Mochi",
        system_prompt: str = "",
        memory: Memory | None = None,
    ) -> None:
        self.adapters = adapters
        self.persona = persona
        self.system_prompt = system_prompt
        self.memory = memory or Memory()
        self.tools = build_tools(self)
        self.history: list[ChatTurn] = []
        self.turns = 0

    def respond(self, text: str) -> str:
        self.turns += 1
        reply = self._respond(text)
        self.history.append(ChatTurn("user", text))
        self.history.append(ChatTurn("assistant", reply))
        return reply

    def _respond(self, text: str) -> str:
        verdict = check_command(text)
        if verdict is not None:
            return verdict

        tool, args = match_tool(self.tools, text)
        if tool is not None:
            return tool.fn(args)

        quick = self._quick_reply(text)
        if quick is not None:
            return quick

        prompt = build_prompt(
            persona=self.persona,
            system_prompt=self.system_prompt,
            memories=self.memory.recall(),
            tools=self.tools,
        )
        response = self.adapters.get().complete(
            prompt=prompt,
            history=[*self.history, ChatTurn("user", text)],
        )
        if response:
            return response
        return "I'm sorry, I couldn't generate a response right now."

    def _quick_reply(self, text: str) -> str | None:
        lowered = text.lower().strip()
        if not lowered:
            return None
        if "time" in lowered:
            return dt.datetime.now().strftime("The time is %H:%M:%S.")
        if lowered.startswith("echo "):
            return text[5:]
        return None

    def health(self) -> dict:
        return {
            "turns": self.turns,
            "adapter": self.adapters.active,
            "memory_entries": self.memory.count(),
            "persona": self.persona,
        }

    def flush(self) -> None:
        self.memory.flush()
