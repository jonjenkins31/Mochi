# plugins/animation_node/plugin_core/zmq_manager.py

"""
Manages ZeroMQ message packing for the animation node.
"""

import struct
import time

# --- Protocol & topics ---
HEADER_FMT = ">HHQI"  # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
CTRL_TOPIC = "ctrl"
HEALTH_TOPIC = b"health"

# --- Reusable buffers ---
packet_buf = None
pixel_buf = None

def ensure_buffers(w: int, h: int):
    """Ensures the reusable pixel and packet buffers are the correct size."""
    global packet_buf, pixel_buf
    need = int(w) * int(h) * 3
    if pixel_buf is None or len(pixel_buf) != need:
        pixel_buf = bytearray(need)
    total = HEADER_SIZE + need
    if packet_buf is None or len(packet_buf) != total:
        packet_buf = bytearray(total)

def pack_frame(w: int, h: int, seq: int, pixels_rgb_bytes: memoryview | bytes | bytearray) -> bytes:
    """Packs a frame into a byte buffer for transmission."""
    ensure_buffers(w, h)
    ts_ms = int(time.time() * 1000)
    struct.pack_into(HEADER_FMT, packet_buf, 0, int(w), int(h), int(ts_ms), int(seq))
    mv = pixels_rgb_bytes if isinstance(pixels_rgb_bytes, memoryview) else memoryview(pixels_rgb_bytes)
    packet_buf[HEADER_SIZE:HEADER_SIZE+len(mv)] = mv
    return packet_buf