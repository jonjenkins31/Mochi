# core/topics.py
"""
Naming helpers for ZeroMQ topics used across Mochi components.

Topics follow a dotted namespace:
    sys.<area>.<name>        -> Host/broker coordination
    node.<node_id>.<signal>  -> Required topics exposed by a plugin/node
    ext.<feature>.<signal>   -> Optional cross-node features (e.g. STT, LLM)

All public helpers here return topics as UTF-8 encoded bytes, which can be
passed directly to ZeroMQ subscribe/send calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


def _normalize(part: str) -> str:
    part = (part or "").strip().lower()
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in part)


def build_topic(*parts: str) -> bytes:
    """Join topic parts (auto-normalising) into a UTF-8 encoded bytes string."""
    normalized = [_normalize(p) for p in parts if p is not None]
    filtered = [p for p in normalized if p]
    topic_str = ".".join(filtered)
    return topic_str.encode("utf-8")


@dataclass(frozen=True)
class NodeTopics:
    """Required topic bundle every node publishes."""

    node_id: str
    frame: bytes
    health: bytes
    event: bytes
    meta: bytes

    def as_strings(self) -> Mapping[str, str]:
        return {
            "frame": self.frame.decode("utf-8"),
            "health": self.health.decode("utf-8"),
            "event": self.event.decode("utf-8"),
            "meta": self.meta.decode("utf-8"),
        }


UNIVERSAL_SIGNAL_SUFFIXES: tuple[str, ...] = ("frame", "health", "event", "meta")


def make_node_topics(node_id: str) -> NodeTopics:
    """Create the required topic bundle for a node id."""
    safe_id = _normalize(node_id) or "node"
    prefix = f"node.{safe_id}"
    topics = [build_topic(prefix, suffix) for suffix in UNIVERSAL_SIGNAL_SUFFIXES]
    return NodeTopics(node_id=safe_id, frame=topics[0], health=topics[1], event=topics[2], meta=topics[3])


def describe_node_catalog(node_topics: NodeTopics, optional_topics: Sequence[bytes] | None = None) -> dict:
    """Produce a JSON-serialisable description for meta announcements."""
    optional_topics = optional_topics or ()
    return {
        "schema": "mochi.node.meta.v1",
        "node_id": node_topics.node_id,
        "required_topics": node_topics.as_strings(),
        "optional_topics": [topic.decode("utf-8") for topic in optional_topics],
    }


# --- Optional / cross-feature topics -----------------------------------------------------------

EXT_STT_TEXT = build_topic("ext", "stt", "text")
EXT_LLM_REPLY = build_topic("ext", "llm", "reply")

SYS_BROADCAST = build_topic("sys", "broadcast")
SYS_ALERT = build_topic("sys", "alert")
