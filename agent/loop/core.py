"""Mochi Tier-1 agent Core.

The chassis constructs this object on the OS main thread. It keeps Mochi's
existing legacy ZMQ topics (`stt.text`, `llm.reply`, etc.) so current animation
and chat surfaces continue to work while the agent becomes a first-class Core
instead of a supervised worker node.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Iterable, Sequence

import zmq

from app.core import Core
from transport import EXT_LLM_REPLY, EXT_STT_TEXT
from transport.messages import (
    Msg,
    TOPIC_LLM_REPLY,
    TOPIC_STT_TEXT,
    build,
)

from agent.adapters.registry import build_adapter_registry
from agent.loop.runtime import AgentRuntime
from transport.node_template import PROJECT_ROOT

DEFAULT_SUBSCRIBE_TOPICS: tuple[bytes, ...] = (EXT_STT_TEXT, TOPIC_STT_TEXT)
DEFAULT_PUBLISH_TOPICS: tuple[bytes, ...] = (EXT_LLM_REPLY, TOPIC_LLM_REPLY)


def _normalize_topics(
    values: Iterable[bytes | str] | None,
    *,
    defaults: Sequence[bytes],
) -> tuple[bytes, ...]:
    topics: list[bytes] = []
    for entry in values or defaults:
        topic = entry if isinstance(entry, bytes) else entry.encode("utf-8")
        topic = topic.strip()
        if topic:
            topics.append(topic)
    return tuple(dict.fromkeys(topics))


def _resolve_node_config(raw_config: dict) -> dict:
    return raw_config.get("node") or raw_config


class AgentCore(Core):
    def __init__(self, *, bus, config: dict, project_root: Path = PROJECT_ROOT):
        super().__init__(bus=bus)
        self.config = _resolve_node_config(config)
        self.project_root = Path(project_root)
        self.node_id = self.config.get("id") or "agent"
        self._bus_sub_address = (
            self.config.get("sub_address")
            or self.config.get("pub_address")
            or os.environ.get("JAEGER_BUS_XPUB")
            or "tcp://127.0.0.1:5555"
        )
        self._bus_pub_address = (
            self.config.get("pub_backend_address")
            or os.environ.get("JAEGER_BUS_XSUB")
            or "tcp://127.0.0.1:5557"
        )
        self._subscribe_topics = _normalize_topics(
            self.config.get("subscribe_topics"), defaults=DEFAULT_SUBSCRIBE_TOPICS)
        self._publish_topics = _normalize_topics(
            self.config.get("publish_topics"), defaults=DEFAULT_PUBLISH_TOPICS)
        if not self._publish_topics:
            raise ValueError("Agent core must publish to at least one topic.")

        self.model = self.config.get("model", "gemma3:12b")
        self.persona = self.config.get("persona", "Mochi")
        self.system_prompt = self._load_system_prompt()
        self.adapters = build_adapter_registry(
            active=self.config.get("adapter", "ollama"),
            ollama_host=self.config.get("ollama_host", "http://localhost:11434"),
            ollama_model=self.model,
            ollama_timeout=float(self.config.get("ollama_timeout", 30)),
        )
        self.runtime = AgentRuntime(
            adapters=self.adapters,
            persona=self.persona,
            system_prompt=self.system_prompt,
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._messages_processed = 0
        self._last_request_ts = 0.0
        self._last_reply_text: str | None = None

    def setup(self) -> None:
        self._thread = threading.Thread(
            target=self._loop, name="agent-core", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.runtime.flush()

    def health(self) -> dict:
        return {
            "model": self.model,
            "messages_processed": self._messages_processed,
            "last_request_ts": self._last_request_ts,
            **self.runtime.health(),
        }

    def _load_system_prompt(self) -> str:
        inline = (self.config.get("system_prompt") or "").strip()
        if inline:
            return inline
        prompt_path = self.config.get("system_prompt_path")
        if not prompt_path:
            return ""
        try:
            return (self.project_root / prompt_path).read_text(
                encoding="utf-8").strip()
        except OSError:
            return ""

    def _loop(self) -> None:
        ctx = zmq.Context.instance()
        sub_socket = ctx.socket(zmq.SUB)
        pub_socket = ctx.socket(zmq.PUB)
        try:
            sub_socket.setsockopt(zmq.LINGER, 0)
            for topic in self._subscribe_topics:
                sub_socket.setsockopt(zmq.SUBSCRIBE, topic)
            sub_socket.connect(self._bus_sub_address)
            pub_socket.setsockopt(zmq.LINGER, 0)
            pub_socket.connect(self._bus_pub_address)
            time.sleep(0.05)
            while not self._stop.is_set():
                try:
                    topic, payload = sub_socket.recv_multipart(flags=zmq.NOBLOCK)
                except zmq.Again:
                    time.sleep(0.02)
                    continue
                except zmq.ZMQError:
                    if self._stop.is_set():
                        break
                    continue
                if topic not in self._subscribe_topics:
                    continue
                try:
                    msg = Msg.from_json(payload)
                except Exception:
                    continue
                self._messages_processed += 1
                self._last_request_ts = time.time()
                reply = self.runtime.respond(msg.text)
                self._last_reply_text = reply
                self._send_reply(pub_socket, reply, request=msg)
        finally:
            try:
                sub_socket.close(linger=0)
                pub_socket.close(linger=0)
            except Exception:
                pass

    def _send_reply(self, pub_socket, reply: str, *, request: Msg) -> None:
        message = build(
            source=self.node_id,
            kind="assistant",
            text=reply,
            request_id=request.id,
        )
        payload = message.to_json()
        for topic in self._publish_topics:
            try:
                pub_socket.send_multipart([topic, payload], copy=True)
            except Exception:
                pass


def make_core(bus, config: dict) -> AgentCore:
    return AgentCore(bus=bus, config=config)
