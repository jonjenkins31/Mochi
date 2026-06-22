"""Safety gates for agent-triggered actions."""

from __future__ import annotations

import re

_FORGET = re.compile(r"\bforget\s+everything\b", re.I)
_FORCE = re.compile(r"\bforce\b", re.I)


def check_command(text: str) -> str | None:
    """Return a refusal string, or None to allow the command."""
    if _FORGET.search(text) and not _FORCE.search(text):
        return (
            "That clears Mochi's memory. Say 'forget everything force' "
            "if you really mean it."
        )
    return None
