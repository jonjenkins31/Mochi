# plugins/animation_node/plugin_core/zmq_manager.py

"""
Manages ZeroMQ message packing and topic configuration for the animation node.
"""

from __future__ import annotations

import struct
import time
from typing import Iterable, Tuple

from transport import NodeTopics, make_node_topics

# --- Protocol ---
HEADER_FMT = ">HHQI"  # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# --- Topic catalogue ---
_topics: NodeTopics = make_node_topics("node")
_optional_topics: Tuple[bytes, ...] = ()


def configure_topics(topics: NodeTopics, optional_topics: Iterable[bytes] | None = None) -> None:
    """Configure the current topic catalog for the node."""
    global _topics, _optional_topics
    _topics = topics
    _optional_topics = tuple(optional_topics or ())


def current_topics() -> NodeTopics:
    """Return the current required topics."""
    return _topics


def optional_topics() -> Tuple[bytes, ...]:
    """Return optional topics advertised by the node."""
    return _optional_topics


# --- Reusable buffers ---
packet_buf = None
pixel_buf = None


def ensure_buffers(w: int, h: int):
    """Ensure the reusable pixel and packet buffers are the correct size."""
    global packet_buf, pixel_buf
    need = int(w) * int(h) * 3
    if pixel_buf is None or len(pixel_buf) != need:
        pixel_buf = bytearray(need)
    total = HEADER_SIZE + need
    if packet_buf is None or len(packet_buf) != total:
        packet_buf = bytearray(total)


def pack_frame(w: int, h: int, seq: int, pixels_rgb_bytes: memoryview | bytes | bytearray) -> bytes:
    """Pack a frame into a byte buffer for transmission."""
    ensure_buffers(w, h)
    ts_ms = int(time.time() * 1000)
    struct.pack_into(HEADER_FMT, packet_buf, 0, int(w), int(h), int(ts_ms), int(seq))
    mv = pixels_rgb_bytes if isinstance(pixels_rgb_bytes, memoryview) else memoryview(pixels_rgb_bytes)
    packet_buf[HEADER_SIZE:HEADER_SIZE + len(mv)] = mv
    return packet_buf
