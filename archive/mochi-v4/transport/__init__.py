"""Mochi transport layer — ZeroMQ bus + topics + node base.

Mirrors JROS's transport/: the bus and its primitives live here so
the rest of the codebase reads as agent/ (cognitive) + nodes/
(peripherals) + transport/ (bus connecting them) + core/ (shared
infrastructure).
"""

from .topics import (
    NodeTopics,
    describe_node_catalog,
    make_node_topics,
    build_topic,
    EXT_LLM_REPLY,
    EXT_STT_TEXT,
    SYS_ALERT,
    SYS_BROADCAST,
)
from .messages import (
    Msg,
    build,
    TOPIC_STT_TEXT,
    TOPIC_LLM_REPLY,
    TOPIC_TTS_SAY,
    TOPIC_TTS_DONE,
    TOPIC_ANIM_EVENT,
    TOPIC_SYS_CMD,
)
from . import zmq_manager


# Lazy-import MochiNodeBase so the transport package stays importable
# even when psutil (a node_base dependency) isn't installed in the
# current venv — useful for tools/scripts that only need topics/messages.
def __getattr__(name):
    if name == "MochiNodeBase":
        from .node_base import MochiNodeBase
        return MochiNodeBase
    raise AttributeError(name)

__all__ = [
    "NodeTopics", "describe_node_catalog", "make_node_topics", "build_topic",
    "EXT_LLM_REPLY", "EXT_STT_TEXT", "SYS_ALERT", "SYS_BROADCAST",
    "Msg", "build",
    "TOPIC_STT_TEXT", "TOPIC_LLM_REPLY", "TOPIC_TTS_SAY", "TOPIC_TTS_DONE",
    "TOPIC_ANIM_EVENT", "TOPIC_SYS_CMD",
    "zmq_manager",
    "MochiNodeBase",
]
