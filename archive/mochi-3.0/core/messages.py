"""Shared message envelope and topic constants for Mochi."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict

# Topic strings
TOPIC_STT_TEXT = b"stt.text"
TOPIC_LLM_REPLY = b"llm.reply"
TOPIC_TTS_SAY = b"tts.say"
TOPIC_TTS_DONE = b"tts.done"
TOPIC_ANIM_EVENT = b"anim.event"
TOPIC_SYS_CMD = b"system.cmd"


def now_s() -> float:
    return time.time()


def new_msg_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Msg:
    """Lightweight JSON envelope used by Mochi services."""

    id: str
    ts: float
    source: str
    kind: str
    text: str = ""
    meta: Dict[str, Any] | None = None

    def to_json(self) -> bytes:
        return json.dumps(asdict(self)).encode("utf-8")

    @staticmethod
    def from_json(data: bytes) -> "Msg":
        obj = json.loads(data.decode("utf-8"))
        return Msg(**obj)


def build(source: str, kind: str, text: str = "", **meta: Any) -> Msg:
    return Msg(id=new_msg_id(), ts=now_s(), source=source, kind=kind, text=text, meta=meta or {})
