# core/zmq_manager.py

"""
Manages ZeroMQ sockets for frame publishing and control.
"""

import zmq
import time
import struct
import logging
import threading

from animations.master_handler import create_animation as create_anim
from core.mscript_engine import MscriptScript
from core.node_state import node_state

logger = logging.getLogger(__name__)

# --- ZMQ constants ---
ctx = zmq.Context.instance()
PUB = zmq.PUB
SUB = zmq.SUB
LINGER = zmq.LINGER
SNDHWM = zmq.SNDHWM

# --- Protocol & topics ---
HEADER_FMT = ">HHQI"  # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
CTRL_TOPIC = "ctrl"
HEALTH_TOPIC = b"health"

shutdown_evt = threading.Event()

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

def control_loop(ctrl_addr):
    """The loop that listens for and processes control commands."""
    sub = ctx.socket(SUB)
    sub.connect(ctrl_addr)
    sub.setsockopt_string(zmq.SUBSCRIBE, CTRL_TOPIC)
    logger.info(f"Control subscriber connected -> {ctrl_addr}, topic='{CTRL_TOPIC}'")
    while not shutdown_evt.is_set():
        try:
            _, msg = sub.recv_multipart()
            parts = msg.decode().strip().split()
            if not parts: continue
            cmd = parts[0].lower()
            if cmd == "mode" and len(parts) >= 2:
                name = " ".join(parts[1:])
                new = create_anim(name, node_state.w, node_state.h)
                node_state.anim, node_state.current_mode = new, name
                logger.info(f"Ctrl: mode -> {name}")
            elif cmd == "size" and len(parts) == 2 and "x" in parts[1].lower():
                w_str, h_str = parts[1].lower().split("x", 1)
                new_w, new_h = int(w_str), int(h_str)
                node_state.w, node_state.h = new_w, new_h
                logger.info(f"Ctrl: resized to {new_w}x{new_h}")
                if node_state.current_mode:
                    try:
                        new_anim = create_anim(node_state.current_mode, new_w, new_h)
                        node_state.anim = new_anim
                        logger.info(f"Reloaded animation '{node_state.current_mode}' with new size.")
                    except Exception as e:
                        logger.error(f"Failed to reload animation '{node_state.current_mode}' after resize: {e}")
            elif cmd == "color" and len(parts) == 4 and node_state.anim:
                r, g, b = map(int, parts[1:])
                if hasattr(node_state.anim, 'set_color'):
                    node_state.anim.set_color((r,g,b))
            elif cmd == "play" and len(parts) >= 2:
                path = " ".join(parts[1:])
                try:
                    node_state.script = MscriptScript(path)
                    logger.info(f"Ctrl: Started script '{path}'")
                except Exception as e:
                    logger.error(f"Failed to start script '{path}': {e}")
                    node_state.script = None
            elif cmd == "stop":
                if node_state.script:
                    logger.info("Ctrl: Script stopped by command")
                    node_state.script = None
            elif cmd == "quit":
                logger.info("Ctrl: quit received"); shutdown_evt.set()
            else:
                logger.warning(f"Ctrl: unknown command: {msg.decode()}")
        except Exception as e:
            logger.error(f"CTRL parse error: {e}")
