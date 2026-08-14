"""A character's voice, composed into a system prompt.

A character pack answers two questions and they belong in one folder:

    how it LOOKS and MOVES     kind, assets, render, motion_scripts
    how it SPEAKS              identity, prompt, lore   ← this file

The render half is JaegerAnimation's — it validates and plays it. This
file reads only the speaking half, which that reader ignores, so the two
coexist in one `character.yaml` without either knowing about the other.

WHAT WAS DELIBERATELY LEFT BEHIND. JaegerAI's character sheet also
carries numeric trait sliders — HEXACO, SPECIAL, Expression, Domains.
They are not imported. An LLM cannot map `sarcasm: 0.40` to behaviour;
those numbers are meaningful as weights for a model trained on them and
inert as prompt text, so carrying them here would be ~1,800 characters
of tokens per turn buying nothing. If a custom net ever wants them, they
are still in JaegerAI where they make sense.

WHAT WAS WORTH TAKING: the persona boundary. Measured, not assumed —
JaegerAI's bench found character traits sitting in the execution context
drift tool arguments and plan lines toward "in character" instead of
literal, and that the tax was real enough to remove persona from the
worker prompt entirely. Mochi has no sub-agents, but it has the same
hazard the moment tools are switched on, so the boundary comes along
with the voice rather than after the first weird tool call.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml

#: Persona applies to what the character SAYS, and to nothing else. Kept
#: verbatim from JaegerAI so the two projects can be compared, and
#: present even while `[config.mind] tools = false` — a prompt that only
#: draws the line once tools appear is a prompt nobody remembers to fix.
PERSONA_BOUNDARY = (
    "THE PERSONA BOUNDARY: this voice is for prose you say to the person "
    "you are talking to, and nothing else. When you call a tool, fill a "
    "tool argument, plan, or write code, drop the persona entirely — "
    "there you are precise and literal."
)

#: Spoken, not written. Mochi's replies go through a text-to-speech
#: engine, so the shape of an answer matters as much as its content.
SPOKEN_STYLE = (
    "You are spoken out loud, so answer in one or two short sentences of "
    "plain conversational English, and never use emoji, markdown, code "
    "blocks, bullet points or numbered lists."
)


def read(root: pathlib.Path) -> dict[str, Any]:
    """The speaking half of `<root>/character.yaml`, or {}.

    Never raises. A pack with no persona is a normal pack — it renders a
    face and says nothing, which is what every Mochi character was
    before this existed.
    """
    path = pathlib.Path(root) / "character.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — the renderer reports a broken pack
        return {}
    return raw if isinstance(raw, dict) else {}


def compose(sheet: dict[str, Any], *, spoken: bool = True) -> str:
    """A character sheet as the system prompt the mind is given.

    Prose only, in the order a reader would want it: who you are, the
    backstory, how you speak, then the two rules. Empty sections are
    dropped rather than emitted as headers with nothing under them —
    a half-written character should cost nothing.
    """
    identity = dict(sheet.get("identity") or {})
    prompt = dict(sheet.get("prompt") or {})
    lore = dict(sheet.get("lore") or {})
    name = str(sheet.get("name") or sheet.get("id") or "").strip()

    parts: list[str] = []
    instructions = str(prompt.get("custom_instructions") or "").strip()
    if instructions:
        parts.append(instructions)
    elif name:
        role = str(identity.get("role") or "").strip()
        parts.append(f"You are {name}" + (f", {role}." if role else "."))

    backstory = str(prompt.get("backstory") or "").strip()
    if backstory:
        parts.append(backstory)

    voice: list[str] = []
    tone = str(identity.get("voice_tone") or "").strip()
    if tone:
        voice.append(f"Your tone is {tone}.")
    for label, key in (("Speech habits", "speech_patterns"),):
        habits = _lines(prompt.get(key))
        if habits:
            voice.append(f"{label}: {'; '.join(habits)}.")
    for label, key in (("You often say things like", "quotes"),
                       ("You care about", "ideals")):
        items = _lines(lore.get(key))
        if items:
            voice.append(f"{label}: {'; '.join(items)}.")
    if voice:
        parts.append(" ".join(voice))

    if spoken:
        parts.append(SPOKEN_STYLE)
    parts.append(PERSONA_BOUNDARY)
    return "\n\n".join(parts)


def _lines(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def resolve(config: dict, character_root: pathlib.Path) -> str:
    """Give the mind the active character's voice. Returns what it got.

    Called before boot, like `jaeger_agent.resolve_model`, because the
    mind node reads its config once at setup. A pack with no persona
    leaves whatever the manifest already said — so the manifest's
    `system_prompt` is the fallback, not a thing this fights with.
    """
    sheet = read(character_root)
    if not (sheet.get("identity") or sheet.get("prompt")):
        return str((config.get("mind") or {}).get("system_prompt", ""))
    composed = compose(sheet)
    config.setdefault("mind", {})["system_prompt"] = composed
    return composed


__all__ = ["PERSONA_BOUNDARY", "SPOKEN_STYLE", "read", "compose", "resolve"]
