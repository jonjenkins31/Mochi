"""Making a plain chat model perform, without giving it tools.

An LLM with no tools can only return text. A character has to change its
face, so something must turn text into actions — and the obvious answer
is tool calls. This is the other answer:

    [happy] Ooh, hi hi! I'm Mochi.
     ↑                ↑
     the face         the line that gets spoken

The model writes one marker; the app applies it and strips it before
synthesis. That is the whole mechanism.

WHY IT IS WORTH DOING THIS WAY. A tool catalogue is ~15,000 tokens
against Mochi's 4096-token window, and even the scoped core set is
~3,600 — so tools cost more context than the conversation. This costs
one line of prompt and one regex, works on a 4B model, and needs no
agentic runtime at all. `[config.mind] tools` stays false and the
character still performs.

WHAT IT CANNOT DO, so the boundary is honest: a marker is a STATEMENT,
not a call. There is no return value, nothing to branch on, and no way
for the model to find out what happened. The moment a character needs to
ask a question of the world and act on the answer — read a file, check
the time, look through the camera — that is a tool, and no amount of
markup substitutes for one. Expression is a statement. Action is a call.

ONLY THE CHARACTER'S OWN VOCABULARY IS ACCEPTED. A model will invent
`[excited]` for a pack that has no such face; an unknown marker is
dropped rather than guessed at, and it never reaches the synthesiser
either way.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

#: A leading `[word]`. Leading only, deliberately: a marker is the
#: character deciding how to say the WHOLE line, and one mid-sentence
#: would be a stage direction nobody can act on. Anything bracketed
#: later is left alone for `speakable()` to deal with.
_MARKER = re.compile(r"^\s*\[\s*([a-z][a-z0-9_]*)\s*\]\s*", re.IGNORECASE)


def perform_block(expressions: Iterable[str]) -> str:
    """The prompt fragment that teaches a model the character's faces.

    Deliberately tiny. This is the entire cost of performing without
    tools, and it has to stay small enough to be obviously cheaper than
    a tool schema.
    """
    faces = [str(e).strip() for e in expressions if str(e).strip()]
    if not faces:
        return ""
    return (
        "You have a face and you may change it. Begin your reply with one "
        "of these in square brackets to show that expression while you "
        "speak: " + ", ".join(faces) + ". Use exactly one, at the very "
        "start, and never mention it in words."
    )


def split(text: str, expressions: Iterable[str]) -> tuple[str, str]:
    """Pull the leading marker off a reply. Returns (expression, line).

    The expression is "" when there was none or it was not one this
    character has. The line always comes back speakable — a marker the
    app cannot use must still not be read aloud, because "open bracket
    excited close bracket" is worse than no expression at all.
    """
    line = text or ""
    match = _MARKER.match(line)
    if not match:
        return "", line.strip()
    line = line[match.end():].strip()
    wanted = match.group(1).lower()
    allowed = {str(e).lower(): str(e) for e in expressions}
    return allowed.get(wanted, ""), line


def prompt_for(character: Any, base: str) -> str:
    """`base` plus this character's expression vocabulary."""
    block = perform_block(getattr(character, "expressions", ()) or ())
    return f"{base}\n\n{block}" if block and base else (base or block)


__all__ = ["perform_block", "split", "prompt_for"]
