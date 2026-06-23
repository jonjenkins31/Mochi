"""jaeger_os.nodes.tts — the TTS node package.

Per-subsystem package shape (matches VoiceLLM's stt/ + tts/ + audio/
layout and JROS's own skills/ pattern).  Components that belong with
the TTS node — SSML preprocessing, voice-resolver helpers, future
backend adapters — live as siblings of ``node.py`` here rather than
polluting the top of ``jaeger_os/nodes/``.
"""

from typing import Any

from .node import Synthesizer, TTSNode

__all__ = ["TTSNode", "Synthesizer", "make_tts_node"]


def make_tts_node(bus: Any, config: dict[str, Any]) -> TTSNode:
    """Chassis-contract factory ``(bus, config) -> TTSNode``.

    J5A wrapper around ``jaeger_os.nodes.runtime.ensure_tts_node``
    (idempotent singleton; warms Kokoro). The chassis ``bus``
    argument is accepted but not propagated until J5B unifies the
    chassis bus with JROS's existing global bus.
    """
    from jaeger_os.nodes.runtime import ensure_tts_node
    return ensure_tts_node(warm=bool(config.get("warm", False)))
