"""JROS client protocol — the single wire contract for surfaces.

"Transports, not endpoints": one protocol, many transports. The Swift app
speaks it over stdio (``jaeger bridge``); the MCP server, a web backend, or
any third-party client speaks the *same* frames over the *same* SDK
(:class:`jaeger_os.interfaces.client.JrosClient`). A future WebSocket transport bridges
the in-process chassis bus to these identical frames — so a new surface is a
transport, not a re-implementation.

Frames are JSON objects, one per line (NDJSON):

  client → agent:
    {"op": "send",    "text": <str>, "session": <str?>}     # run one turn
    {"op": "respond", "id": <str>,   "answer": <str>}       # answer a request
    {"op": "quit"}                                          # graceful stop

  agent → client:
    {"type": "ready",   "instance": <str>, "model": <str?>}
    {"type": "state",   "busy": <bool>,    "session": <str?>}
    {"type": "tool",    "name": <str>, "phase": <start|done|error>,
                        "elapsed_s": <float>, "session": <str?>}
    {"type": "reply",   "text": <str>, "error": <str?>, "session": <str?>}
    {"type": "request", "id": <str>, "kind": <approval|clarify|secret>,
                        "prompt": <str>, "options": [<str>...], "session": <str?>}
    {"type": "fatal",   "error": <str>}                     # boot failed

This module is the ONE place these shapes live: the bridge builds them, the
client parses them, and the bus↔wire codec (``event_to_frame``) maps chassis
messages onto them. ``PROTOCOL_VERSION`` bumps on any breaking change.
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = "1"

# ── agent → client frame builders (used by the bridge / any transport) ──


def ready_frame(instance: str, model: str | None) -> dict[str, Any]:
    return {"type": "ready", "instance": instance, "model": model}


def state_frame(busy: bool, session: str = "") -> dict[str, Any]:
    return {"type": "state", "busy": busy, "session": session}


def tool_frame(name: str, phase: str, elapsed_s: float = 0.0,
               session: str = "") -> dict[str, Any]:
    return {"type": "tool", "name": name, "phase": phase,
            "elapsed_s": float(elapsed_s), "session": session}


def reply_frame(text: str, error: str | None = None,
                session: str = "") -> dict[str, Any]:
    return {"type": "reply", "text": text, "error": error, "session": session}


def request_frame(id: str, kind: str, prompt: str,
                   options: tuple[str, ...] | list[str] = (),
                   session: str = "") -> dict[str, Any]:
    return {"type": "request", "id": id, "kind": kind, "prompt": prompt,
            "options": list(options), "session": session}


def fatal_frame(error: str) -> dict[str, Any]:
    return {"type": "fatal", "error": error}


# ── client → agent op builders (used by the client SDK) ──


def send_op(text: str, session: str = "") -> dict[str, Any]:
    return {"op": "send", "text": text, "session": session}


def respond_op(id: str, answer: str) -> dict[str, Any]:
    return {"op": "respond", "id": id, "answer": answer}


def quit_op() -> dict[str, Any]:
    return {"op": "quit"}


# ── parsing ──


def parse(line: str) -> dict[str, Any] | None:
    """Parse one NDJSON line into a frame dict, or None if malformed / not a
    protocol frame (no ``type``/``op`` discriminator)."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict) or not ("type" in obj or "op" in obj):
        return None
    return obj


def encode(frame: dict[str, Any]) -> str:
    """Serialize a frame to one NDJSON line (newline included)."""
    return json.dumps(frame, ensure_ascii=False) + "\n"


# ── chassis-bus message → wire frame (for bus-attached transports) ──


def event_to_frame(msg: Any) -> dict[str, Any] | None:
    """Map a chassis ``/sense/*`` message to a wire frame, or None if the
    message isn't part of the client protocol. Lets a WebSocket/socket
    transport mirror the in-process bus to remote clients identically."""
    topic = getattr(msg, "topic", "")
    session = getattr(msg, "session", "") or ""
    if topic == "/sense/chat":
        return reply_frame(getattr(msg, "text", ""), None, session)
    if topic == "/sense/agent_state":
        return state_frame(getattr(msg, "state", "") == "thinking", session)
    if topic == "/sense/tool":
        return tool_frame(getattr(msg, "name", ""), getattr(msg, "phase", "start"),
                          getattr(msg, "elapsed_s", 0.0), session)
    if topic == "/sense/request":
        return request_frame(getattr(msg, "id", ""), getattr(msg, "kind", "approval"),
                             getattr(msg, "prompt", ""),
                             getattr(msg, "options", ()), session)
    return None
