"""jaeger_os.nodes.software.audio_session — realtime voice-input node package."""

from typing import Any

from .node import AudioSessionNode, STTAdapter, STTNode

__all__ = [
    "AudioSessionNode", "STTNode", "STTAdapter",
    "make_audio_session_node",
]


def make_audio_session_node(bus: Any, config: dict[str, Any]) -> AudioSessionNode:
    """Chassis-contract factory ``(bus, config) -> AudioSessionNode``.

    J5A wrapper around ``jaeger_os.nodes.runtime.ensure_audio_session_node``.
    The audio session has heavy config (AudioSessionConfig dataclass)
    that the runtime singleton expects; J5A passes
    ``AudioSessionConfig()`` defaults — J5B will route the manifest's
    config_key slice through the dataclass.
    """
    from jaeger_os.core.audio import AudioSessionConfig
    from jaeger_os.nodes.runtime import ensure_audio_session_node
    return ensure_audio_session_node(config=AudioSessionConfig())
