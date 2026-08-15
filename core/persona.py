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

from core.module_support import config_of

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

#: What the CHANNEL can carry, which is not a character trait and not a
#: limit on the model. Both ends need it: a speech engine reads "**" out
#: loud, and the transcript is plain text that would show it literally.
#: So it applies whether or not a voice is running.
PLAIN_TEXT = (
    "Write plain conversational English with no emoji, markdown, code "
    "blocks, bullet points or numbered lists — neither the voice nor the "
    "transcript can render them."
)

#: Only while something is actually SPEAKING. This was the line that
#: broke it: "answer in one or two short sentences" was read as a
#: capability, and "tell me a story" came back as "I cannot tell a
#: story". It is a default now, and it says so.
SPOKEN_STYLE = (
    "You are being spoken out loud, so keep ORDINARY answers to a "
    "sentence or two. This is about pacing, not permission — when you "
    "are asked for something longer, give it in full."
)

#: The rule that outranks every other line in the prompt, including the
#: character's own. A persona is how a thing SOUNDS, and a voice that
#: refuses work is not a character, it is a broken assistant wearing
#: one. Stated positively AND negatively because the failure was a model
#: inferring a limit that nobody wrote down.
NO_LIMIT = (
    "YOUR CHARACTER IS A VOICE, NEVER A LIMIT. It shapes how you say "
    "things; it never decides what you are willing to do. Do everything "
    "you are asked, in character — tell the story, write the list, "
    "explain at length. Never refuse or shorten a request because of "
    "your personality, your tone, or the kind of thing you are."
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

    parts.append(PLAIN_TEXT)
    if spoken:
        parts.append(SPOKEN_STYLE)
    parts.append(PERSONA_BOUNDARY)
    # LAST, so it is the most recent instruction the model reads and the
    # one it weighs hardest. Everything above is style; this is the rule
    # that style may not override.
    parts.append(NO_LIMIT)
    return "\n\n".join(parts)


def _lines(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def speaking(app: Any) -> bool:
    """Is anything actually going to SAY this?

    The spoken style asks for one or two short sentences, which is right
    for a voice and wrong for a text box: it is why "tell me a story"
    came back as "I cannot tell a story". So it is applied only when a
    voice is running — a chat window gets prose, and turning the
    speakers on re-voices the mind to match.
    """
    try:
        from core import audio_switch

        return bool(audio_switch.state(app)[1])
    except Exception:  # noqa: BLE001
        return False


def resolve(config: dict, character_root: pathlib.Path) -> str:
    """Give the mind the active character's voice. Returns what it got.

    Called before boot, like `jaeger_agent.resolve_model`, because the
    mind node reads its config once at setup. A pack with no persona
    leaves whatever the manifest already said — so the manifest's
    `system_prompt` is the fallback, not a thing this fights with.
    """
    sheet = read(character_root)
    if not (sheet.get("identity") or sheet.get("prompt")):
        # Nothing to say in this pack, so nothing is said FOR it. The
        # manifest's `system_prompt` is the operator's own override and
        # is left exactly as found — empty by default, which means the
        # model behind the character arrives unfiltered.
        return str((config.get("mind") or {}).get("system_prompt", ""))
    # Boot: no node is running yet, so nothing can be speaking.
    composed = compose(sheet, spoken=False)
    config.setdefault("mind", {})["system_prompt"] = composed
    return composed


def apply(app: Any, character_root: pathlib.Path,
          spoken: bool | None = None) -> str:
    """Give a RUNNING mind the character's voice. Returns what it got.

    `resolve()` is the boot-time half — it edits config before any node
    is built. This is the live half, for switching character while the
    app is up: the composed prompt goes into the config (so a node built
    later starts in the right voice) AND into the agent that is already
    running (so the next thing it says is in that voice, with no model
    reload).

    A pack with no persona leaves the mind alone rather than blanking
    it — the same rule `resolve()` follows, so switching to a face-only
    character keeps whatever voice was already there instead of
    silencing it.
    """
    sheet = read(character_root)
    if not (sheet.get("identity") or sheet.get("prompt")):
        return ""
    composed = compose(sheet,
                       spoken=speaking(app) if spoken is None else spoken)
    try:
        config_of(app).setdefault("mind", {})["system_prompt"] = composed
    except Exception:  # noqa: BLE001
        pass
    from modules import jaeger_agent as mind

    mind.set_persona(app, composed)
    return composed


__all__ = [
    "PERSONA_BOUNDARY", "SPOKEN_STYLE", "PLAIN_TEXT", "NO_LIMIT",
    "read", "compose", "resolve", "apply",
    "speaking",
]
