"""Compatibility shim for the renamed audio session node package."""

from jaeger_os.nodes.audio_session import AudioSessionNode, STTAdapter, STTNode

__all__ = ["AudioSessionNode", "STTNode", "STTAdapter"]
