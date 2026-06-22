"""Small persistent memory store for Mochi's agent."""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / ".run" / "agent_memory.jsonl"


class Memory:
    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        self.path = path
        self._notes = self._load()

    def _load(self) -> list[str]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        notes: list[str] = []
        for line in lines:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            note = item.get("note")
            if isinstance(note, str):
                notes.append(note)
        return notes

    def remember(self, note: str) -> None:
        if note:
            self._notes.append(note)

    def recall(self) -> list[str]:
        return list(self._notes)

    def clear(self) -> None:
        self._notes.clear()

    def count(self) -> int:
        return len(self._notes)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(json.dumps({"note": note}) for note in self._notes)
        self.path.write_text((text + "\n") if text else "", encoding="utf-8")
