# mochi_node.py

"""
The main entry point for the Mochi display node.

This script initializes the node, loads the configuration, and runs the main
loop that renders animations and processes commands.
"""

import time
import signal
import logging
import json
import yaml
import os
import psutil
import threading
import numpy as np

from animations import create_animation
from core.mochi_animations import Animation
from core.logging_utils import setup_logger
from core.node_state import node_state
from core.command_processor import process_command
from core.mochi_script_engine import load_script
from core import zmq_manager

# The root directory of the Mochi project.
# Assumes that this script (mochi_node.py) is located at the project root.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

class SolidColorAnimation(Animation):
    """A simple fallback animation that fills the screen with a solid color."""
    def __init__(self, w, h, color=(0, 0, 0)):
        super().__init__(w, h)
        self.color = color

    def render_into(self, t: float, pixel_buf: bytearray):
        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        frame[:, :] = self.color

def main():
    """The main function for the Mochi node."""
    logger = setup_logger("MochiNode")

    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Cannot load config.yaml: {e}")
        return

    # --- Load configuration ---
    node_config = config.get("node", {})
    node_state.w = node_config.get("logical_width", 64)
    node_state.h = node_config.get("logical_height", 64)
    fps = node_config.get("fps", 60)
    pub_addr = node_config.get("pub_address", "tcp://127.0.0.1:5555")
    ctrl_addr = node_config.get("ctrl_address", "tcp://127.0.0.1:5556")
    default_script = node_config.get("default_script")

    process = psutil.Process(os.getpid())

    # --- Set up signal handling for graceful shutdown ---
    def _sig_handler(_s, _f):
        zmq_manager.shutdown_evt.set()
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    # --- Start the control loop in a separate thread ---
    threading.Thread(target=zmq_manager.control_loop, args=(ctrl_addr,), daemon=True).start()

    # --- Set up the frame publisher ---
    pub = zmq_manager.ctx.socket(zmq_manager.PUB)
    pub.setsockopt(zmq_manager.LINGER, 0)
    pub.setsockopt(zmq_manager.SNDHWM, 2)
    pub.bind(pub_addr)
    time.sleep(0.1)
    logger.info(f"Publisher bound -> {pub_addr}; logical_size={node_state.w}x{node_state.h}; FPS={fps}")

    # --- Load the default animation/script ---
    # Set a fallback animation
    light_blue = (173, 216, 230)
    node_state.anim = SolidColorAnimation(node_state.w, node_state.h, color=light_blue)
    node_state.current_mode = "solid_color"
    logger.info(f"Defaulting to solid color {light_blue}")

    # Load default script if specified
    if default_script:
        logger.info(f"Loading default script: {default_script}")
        try:
            # Manually load the script object, bypassing the command processor
            # for the initial 'play' action, which is not a standard command.
            node_state.script = load_script(os.path.join(PROJECT_ROOT, default_script))
            logger.info(f"Default script '{default_script}' loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load default script '{default_script}': {e}")

    # --- Main render loop ---
    seq = 0
    clock = time.perf_counter
    next_frame = clock()
    dt = 1.0 / float(fps)
    last_health_t = 0.0
    bytes_sent_since_health = 0
    try:
        while not zmq_manager.shutdown_evt.is_set():
            now = clock()
            if now < next_frame:
                time.sleep(max(0.0, next_frame - now))
            
            # --- Run script if active ---
            if node_state.script:
                # Use the project root to resolve asset paths inside the script.
                due_commands = node_state.script.update(time.time())
                for command in due_commands:
                    process_command(command, resolve_dir=PROJECT_ROOT)

            if node_state.anim is None:
                continue

            # --- Render the current animation ---
            zmq_manager.ensure_buffers(node_state.w, node_state.h)
            try:
                node_state.anim.render_into(time.time(), zmq_manager.pixel_buf)
            except Exception as e:
                logger.error(f"frame() error from '{node_state.current_mode}': {e}")
                error_color_bytes = b'\x80\x00\x00'
                zmq_manager.pixel_buf[:] = error_color_bytes * (node_state.w * node_state.h)

            # --- Pack and publish the frame ---
            packed_bytes = zmq_manager.pack_frame(node_state.w, node_state.h, seq, zmq_manager.pixel_buf)
            pub.send_multipart([zmq_manager.FRAME_TOPIC, packed_bytes], copy=False)
            bytes_sent_since_health += len(packed_bytes)

            # --- Send periodic health check ---
            now_wall = time.time()
            if now_wall - last_health_t >= 1.0:
                mem_info = process.memory_info()
                tx_rate_mbps = (bytes_sent_since_health / (now_wall - last_health_t)) / (1024*1024)
                hb = {
                    "ts": int(now_wall * 1000), "seq": seq,
                    "w": node_state.w, "h": node_state.h,
                    "fps": fps, "mode": node_state.current_mode or "?",
                    "mem_mb": mem_info.rss / (1024 * 1024),
                    "tx_rate_mbps": tx_rate_mbps
                }
                pub.send_multipart([zmq_manager.HEALTH_TOPIC, json.dumps(hb).encode("utf-8")])
                last_health_t = now_wall
                bytes_sent_since_health = 0

            seq += 1
            next_frame += dt
    finally:
        try:
            pub.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
