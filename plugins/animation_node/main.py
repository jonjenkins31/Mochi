# plugins/animation_node/main.py

"""
The main entry point for the Mochi Animation Node plugin.

This script initializes the node, loads its configuration, and runs the main
loop that renders animations and processes commands received via ZMQ.
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
import zmq

# Since this script is in a subdirectory, we need to add the plugin's root to the Python path
# to ensure that imports like 'from animations import ...' work correctly.
import sys
PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.append(PLUGIN_ROOT)

from animations import create_animation
from plugin_core.mochi_animations import Animation, Command
from plugin_core.logging_utils import setup_logger
from plugin_core.mscript_engine import MscriptScript
from core import zmq_manager # This will be the plugin's own ZMQ handling.

class AnimationNode:
    """
    Manages the state and logic for rendering animations.
    """
    def __init__(self, config, project_root):
        self.logger = logging.getLogger("AnimationNode")
        self.project_root = project_root

        # Load configuration
        self.w = config.get("logical_width", 64)
        self.h = config.get("logical_height", 64)
        self.fps = config.get("fps", 60)
        env = os.environ
        self.pub_addr = env.get("MOCHI_BROKER_XPUB", config.get("pub_address", "tcp://127.0.0.1:5555"))
        self.pub_backend_addr = env.get("MOCHI_BROKER_XSUB", config.get("pub_backend_address"))
        self.ctrl_addr = env.get("MOCHI_NODE_CTRL_ADDR", config.get("ctrl_address", "tcp://127.0.0.1:5556"))
        default_script = config.get("default_script")

        # Set a fallback animation
        light_blue = (173, 216, 230)
        self.anim = SolidColorAnimation(self.w, self.h, color=light_blue)
        self.current_mode = "solid_color"
        self.keyframes: dict[int, Animation] = {}
        self.logger.info(f"Defaulting to solid color {light_blue}")

        # Load default script if specified
        self.script = None
        if default_script:
            self.logger.info(f"Loading default script: {default_script}")
            try:
                script_path = os.path.join(self.project_root, default_script)
                self.script = MscriptScript(script_path)
                self.logger.info(f"Default script '{default_script}' loaded successfully.")
            except Exception as e:
                self.logger.error(f"Failed to load default script '{default_script}': {e}")

    def process_command(self, msg):
        """Processes an incoming command from either ZMQ or a running script."""
        if isinstance(msg, Command):
            self._process_script_command(msg)
            return
        if not isinstance(msg, str):
            self.logger.warning(f"Ctrl: unsupported command type {type(msg)!r}")
            return

        parts = msg.strip().split()
        if not parts: return
        cmd = parts[0].lower()
        self.logger.info(f"Ctrl: Received command: {msg}")

        try:
            if cmd == "mode" and len(parts) >= 2:
                name = " ".join(parts[1:])
                new = create_animation(name, self.w, self.h)
                self.anim, self.current_mode = new, name
                self.logger.info(f"Ctrl: mode -> {name}")
            elif cmd == "size" and len(parts) == 2 and "x" in parts[1].lower():
                w_str, h_str = parts[1].lower().split("x", 1)
                new_w, new_h = int(w_str), int(h_str)
                self.w, self.h = new_w, new_h
                self.logger.info(f"Ctrl: resized to {new_w}x{new_h}")
                if self.current_mode:
                    new_anim = create_animation(self.current_mode, new_w, new_h)
                    self.anim = new_anim
                    self.logger.info(f"Reloaded animation '{self.current_mode}' with new size.")
            elif cmd == "color" and len(parts) == 4 and self.anim:
                r, g, b = map(int, parts[1:])
                if hasattr(self.anim, 'set_color'):
                    self.anim.set_color((r,g,b))
            elif cmd == "play" and len(parts) >= 2:
                path = os.path.join(self.project_root, " ".join(parts[1:]))
                self.script = MscriptScript(path)
                self.logger.info(f"Ctrl: Started script '{path}'")
            elif cmd == "stop":
                if self.script:
                    self.logger.info("Ctrl: Script stopped by command")
                    self.script = None
            else:
                self.logger.warning(f"Ctrl: unknown command: {msg}")
        except Exception as e:
            self.logger.error(f"CTRL parse error: {e}")

    def _process_script_command(self, command: Command):
        """Handles structured commands emitted by an active script."""
        name = (command.name or "").upper()
        args = dict(command.args or {})

        key_id = args.get("K")
        key_int = None
        if key_id is not None:
            try:
                key_int = int(key_id)
                args["K"] = key_int
            except (TypeError, ValueError):
                self.logger.warning(f"Script: invalid key id '{key_id}' for command {name}")
                key_int = None

        # Separate event commands from animation loads
        event_name = args.pop("EVENT", None)

        if event_name and key_int is not None:
            target_anim = self.keyframes.get(key_int)
            if not target_anim:
                self.logger.warning(f"Script: EVENT '{event_name}' for unknown key {key_int}")
                return
            try:
                payload_args = {k: v for k, v in args.items() if k != "K"}
                target_anim.on_event(event_name, **payload_args)
                self.anim = target_anim  # Ensure the active animation is in sync
                self.current_mode = f"{name}[{key_int}]"
            except Exception as e:
                self.logger.error(f"Script: event '{event_name}' failed for key {key_int}: {e}")
            return

        # Prepare kwargs for the animation factory
        anim_kwargs = {k: v for k, v in args.items() if k != "K"}
        anim_kwargs["resolve_dir"] = self.project_root

        try:
            new_anim = create_animation(name, self.w, self.h, **anim_kwargs)
        except Exception as e:
            self.logger.error(f"Script: failed to create animation '{name}' with args {anim_kwargs}: {e}")
            return

        if key_int is not None:
            self.keyframes[key_int] = new_anim

        self.anim = new_anim
        self.current_mode = f"{name}[{key_int}]" if key_int is not None else name

    def update(self, timestamp):
        """Updates the active script."""
        if self.script:
            due_commands = self.script.update(timestamp)
            for command in due_commands:
                # Process script commands internally
                self.process_command(command)

    def render(self, timestamp):
        """Renders the current animation into a pixel buffer."""
        zmq_manager.ensure_buffers(self.w, self.h)
        try:
            self.anim.render_into(timestamp, zmq_manager.pixel_buf)
        except Exception as e:
            self.logger.error(f"frame() error from '{self.current_mode}': {e}")
            error_color_bytes = b'\x80\x00\x00'
            zmq_manager.pixel_buf[:] = error_color_bytes * (self.w * self.h)
        return zmq_manager.pixel_buf

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
    
    # Change the working directory to the plugin's root
    os.chdir(PLUGIN_ROOT)

    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Cannot load config.yaml: {e}")
        return

    node_config = config.get("node", {})
    node = AnimationNode(node_config, PLUGIN_ROOT)

    process = psutil.Process(os.getpid())
    shutdown_evt = threading.Event()

    def _sig_handler(_s, _f):
        shutdown_evt.set()
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    # --- ZMQ setup ---
    ctx = zmq.Context.instance()

    # Control loop thread
    def control_loop(ctrl_addr):
        pull_socket = ctx.socket(zmq.PULL)
        pull_socket.bind(ctrl_addr)
        logger.info(f"Control socket listening (PULL) -> {ctrl_addr}")
        try:
            while not shutdown_evt.is_set():
                try:
                    msg = pull_socket.recv_string()
                    if msg.strip().lower() == "quit":
                        logger.info("Ctrl: quit received")
                        shutdown_evt.set()
                    else:
                        node.process_command(msg)
                except zmq.error.ZMQError as e:
                    ctx_term_err = getattr(zmq.error, "ContextTerminated", None)
                    if ctx_term_err and isinstance(e, ctx_term_err):
                        break
                    if e.errno == getattr(zmq, "ETERM", None):
                        break
                    if shutdown_evt.is_set():
                        break
                    logger.error(f"CTRL parse error: {e}")
                except Exception as e:
                    if shutdown_evt.is_set():
                        break
                    logger.error(f"CTRL parse error: {e}")
        finally:
            pull_socket.close(linger=0)
    
    threading.Thread(target=control_loop, args=(node.ctrl_addr,), daemon=True).start()

    # Frame publisher
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.LINGER, 0)
    pub.setsockopt(zmq.SNDHWM, 2)
    if node.pub_backend_addr:
        pub.connect(node.pub_backend_addr)
        logger.info(f"Publisher connected -> {node.pub_backend_addr}")
    else:
        pub.bind(node.pub_addr)
        logger.info(f"Publisher bound -> {node.pub_addr}")
    time.sleep(0.1)
    logger.info(f"Publisher ready; logical_size={node.w}x{node.h}; FPS={node.fps}")

    # --- Main render loop ---
    seq = 0
    clock = time.perf_counter
    next_frame = clock()
    dt = 1.0 / float(node.fps)
    last_health_t = 0.0
    bytes_sent_since_health = 0
    try:
        while not shutdown_evt.is_set():
            now = clock()
            if now < next_frame:
                time.sleep(max(0.0, next_frame - now))
            
            node.update(time.time())

            if node.anim is None:
                continue

            rendered_pixels = node.render(time.time())
            
            packed_bytes = zmq_manager.pack_frame(node.w, node.h, seq, rendered_pixels)
            pub.send_multipart([zmq_manager.FRAME_TOPIC, packed_bytes], copy=False)
            bytes_sent_since_health += len(packed_bytes)

            now_wall = time.time()
            if now_wall - last_health_t >= 1.0:
                mem_info = process.memory_info()
                tx_rate_mbps = (bytes_sent_since_health / (now_wall - last_health_t)) / (1024*1024) if now_wall > last_health_t else 0
                hb = {
                    "ts": int(now_wall * 1000), "seq": seq,
                    "w": node.w, "h": node.h,
                    "fps": node.fps, "mode": node.current_mode or "?",
                    "mem_mb": mem_info.rss / (1024 * 1024),
                    "tx_rate_mbps": tx_rate_mbps
                }
                pub.send_multipart([zmq_manager.HEALTH_TOPIC, json.dumps(hb).encode("utf-8")])
                last_health_t = now_wall
                bytes_sent_since_health = 0

            seq += 1
            next_frame += dt
    finally:
        shutdown_evt.set()
        logger.info("Shutting down plugin.")
        try:
            pub.close()
            ctx.term()
        except Exception as e:
            logger.error(f"Error during ZMQ shutdown: {e}")

if __name__ == "__main__":
    main()
