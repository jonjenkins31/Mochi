"""The mind — how Mochi uses the agent module.

    slot: mind               jaeger-agent fills it today
    consumes  /act/chat
    produces  /sense/chat, /sense/agent_state

OPTIONAL, like the voice and the ears. A character that cannot hold a
conversation is still a character — that is exactly what v5.2 was — so
nothing here raises when the module is absent.

A CHATBOT, NOT AN AGENT
-----------------------
jaeger-agent is a full agentic runtime: ~96 tools that read files, run
code, schedule work and browse. Mochi wants none of it. It wants a
character that answers when you talk to it, so this integration takes
the bare loop and leaves the tools on the shelf.

That is `chat_only()`, and it is not cosmetic. The tools register
themselves at IMPORT time, and ~96 schemas are ~15,000 tokens on every
turn against the 4096-token window in jaeger.toml — the catalogue does
not fit beside a conversation, let alone leave room for an answer. The
module offers `JAEGER_AGENT_NO_TOOLS` for exactly this embedder, and
there is no config key for it: by the time the framework reads
`[config.mind]` the package is already imported. So it is an
environment variable, set before boot, from main().

Like the voice, this integration deliberately carries the provider's
real import name. If Mochi imports a different mind module later, give
that provider its own named file rather than generalising this one —
an operator should be able to see which brain is in use.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

from core.module_support import installed

SLOT = "mind"

#: The exact import package integrated by this module file.
PACKAGE = "jaeger_agent"

#: The environment switch that turns the agent into a chatbot.
NO_TOOLS_ENV = "JAEGER_AGENT_NO_TOOLS"

# The chat topics belong to jaeger-agent, not to jaeger_os.topics, so
# they cannot be imported from the framework — and they must be nameable
# with the module ABSENT, which is the whole point of an optional slot.
# Duplicated as literals for that reason; `test_mind_topics_match_the_module`
# fails if the module ever renames one, so the copy cannot drift silently.
CHAT_SAY = "/act/chat"            #: a turn from the operator
CHAT_REPLY = "/sense/chat"        #: the answer
AGENT_STATE = "/sense/agent_state"  #: thinking / idle — what drives a spinner

#: What a surface watches to follow one turn end to end.
WATCH = (CHAT_SAY, CHAT_REPLY, AGENT_STATE)


def available() -> bool:
    return installed(PACKAGE)


def chat_only(enabled: bool = True) -> None:
    """Ask for the bare loop, before anything imports the package.

    Call this from main() BEFORE the framework touches jaeger_os:
    module discovery imports every installed module's package to read
    its manifest, so by the time a node boots the decision is already
    made. `setdefault`, not assignment — an operator who exported the
    variable themselves outranks this app.

    A SWITCH, NOT A WALL. `enabled=False` leaves the full agent
    installed: ~96 tools, including `look_at` for a local VLM, `speak`,
    `listen` and `ocr`. Mochi's default is the chatbot because a desk
    character wants conversation, but that is a CHOICE this app makes
    and the manifest states — `[config.mind] tools` — not a limit built
    into the composition. Nothing downstream of here assumes the bare
    loop, so flipping it does not require unpicking anything.

    The catalogue needs room: ~96 schemas are ~15,000 tokens, so raise
    `ctx` past 16384 or set JAEGER_TOOLSET_SCOPING=1 for the ~17-tool
    core set. The module says so itself in its own __init__.
    """
    if enabled:
        os.environ.setdefault(NO_TOOLS_ENV, "1")


#: Where a GGUF usually already is. `$JAEGER_GGUF` wins over all of them.
MODEL_DIRS = (
    pathlib.Path.home() / ".cache" / "jaeger" / "models",
    pathlib.Path.home() / ".lmstudio" / "models",
    pathlib.Path.home() / "models",
)


def find_model() -> str:
    """Locate weights, so the Chat tab works without editing jaeger.toml.

    An app that cannot start without a path pasted into a manifest is a
    worse app. This looks where models usually already are, including
    LM Studio's cache — anyone running a local model probably has one.
    """
    env = os.environ.get("JAEGER_GGUF", "").strip()
    if env:
        return env
    for root in MODEL_DIRS:
        if not root.is_dir():
            continue
        # mmproj-* are multimodal PROJECTORS, not models. llama.cpp
        # loads one and aborts the PROCESS rather than saying so, which
        # takes the window with it.
        found = [p for p in root.rglob("*.gguf")
                 if not p.name.startswith("mmproj-")]
        if found:
            # SMALLEST, not first alphabetically. Both are arbitrary, but
            # only one of them makes an unconfigured first launch load
            # 13 GB when a 5 GB model is sitting beside it. Pin a
            # specific one with `model_path` in jaeger.toml.
            return str(min(found, key=lambda p: p.stat().st_size))
    return ""


def resolve_model(config: dict) -> str:
    """Fill a `model_path` the manifest left blank. Returns what will load.

    Called from main() before boot, because the node reads its config
    once at setup and there is no second chance. A served provider
    names its own model, so there is nothing to look for.
    """
    if str(config.get("provider", "llama_cpp")) != "llama_cpp":
        return str(config.get("model", ""))
    path = str(config.get("model_path") or "").strip() or find_model()
    config["model_path"] = path
    return path


def set_persona(app: Any, prompt: str) -> bool:
    """Re-voice the running mind. True if it took.

    Switching character has to change what the mind SOUNDS like, not
    just what it looks like — and it must not cost a model reload. It
    does not: the agent reads `self.system_prompt` per turn rather than
    baking it in, so both halves of this are assignments.

        runtime.config.system_prompt   seeds sessions built later —
                                       "New conversation" makes one
        each live agent                the conversation already open

    Reaching into the running node rather than going over a topic,
    because jaeger-agent exposes no topic for it. Allowed HERE and
    nowhere else: this file exists to be the single named place Mochi
    touches this provider, the same licence
    `modules/jaeger_whisper_stt.py` uses for the ears' pause. A tab
    calls `core.persona.apply()`, never this.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return False
    supervisor = getattr(app, "supervisor", None)
    getter = getattr(supervisor, "node", None)
    if getter is None:
        return False
    try:
        runtime = getattr(getter(SLOT), "runtime", None)
        if runtime is None:
            return False
        config = getattr(runtime, "config", None)
        if config is not None and hasattr(config, "system_prompt"):
            config.system_prompt = prompt
        for agent in dict(getattr(runtime, "_sessions", {}) or {}).values():
            if hasattr(agent, "system_prompt"):
                agent.system_prompt = prompt
    except Exception:  # noqa: BLE001 — a voice change never kills a turn
        return False
    return True


def ask(bus: Any, text: str, *, session: str = "mochi") -> bool:
    """Publish one conversational turn. True if it went out.

    The session id is what keeps the transcript coherent across turns —
    the module owns the history, so Mochi never assembles a prompt or
    replays what was already said.
    """
    text = (text or "").strip()
    if not text or not available():
        return False
    from jaeger_agent.messages import ChatMessage

    bus.publish(ChatMessage(text=text, source="mochi", session=session))
    return True


__all__ = [
    "SLOT", "PACKAGE", "NO_TOOLS_ENV", "WATCH", "MODEL_DIRS",
    "CHAT_SAY", "CHAT_REPLY", "AGENT_STATE",
    "available", "chat_only", "ask", "find_model", "resolve_model",
    "set_persona",
]
