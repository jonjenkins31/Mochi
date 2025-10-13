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
from typing import Sequence
import numpy as np
import zmq

# Since this script is in a subdirectory, we need to add the plugin's root to the Python path
# to ensure that imports like 'from animations import ...' work correctly.
import sys
from pathlib import Path
from queue import Empty, SimpleQueue

PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_ROOT not in sys.path:
    sys.path.append(PLUGIN_ROOT)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.append(PROJECT_ROOT_STR)

from animations import create_animation
from plugin_core.mochi_animations import Animation, Command
from plugin_core.logging_utils import setup_logger
from plugin_core.mscript_engine import MscriptScript
from plugin_core import zmq_manager  # This will be the plugin's own ZMQ handling.
from core import describe_node_catalog, make_node_topics


def _merge_dicts(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged

class AnimationNode:
    """Manages the state and logic for rendering animations."""

    def __init__(self, node_id: str, config: dict, project_root: str, optional_topics: Sequence[bytes] | None = None):
        self.project_root = project_root
        self.node_id = node_id
        self.topics = make_node_topics(node_id)
        self.optional_topics = tuple(optional_topics or ())
        zmq_manager.configure_topics(self.topics, optional_topics=self.optional_topics)

        self.logger = logging.getLogger(f"AnimationNode[{self.node_id}]")

        # Configuration & transport endpoints
        self.w = config.get("logical_width", 64)
        self.h = config.get("logical_height", 64)
        self.fps = config.get("fps", 60)
        env = os.environ
        self.pub_addr = env.get("MOCHI_BROKER_XPUB", config.get("pub_address", "tcp://127.0.0.1:5555"))
        self.pub_backend_addr = env.get("MOCHI_BROKER_XSUB", config.get("pub_backend_address"))
        self.ctrl_addr = env.get("MOCHI_NODE_CTRL_ADDR", config.get("ctrl_address", "tcp://127.0.0.1:5556"))
        self.default_script = config.get("default_script")

        self.anim: Animation | None = None
        self.current_mode: str | None = None
        self.current_mode_name: str | None = None
        self.keyframes: dict[int, Animation] = {}
        self.script: MscriptScript | None = None
        self._event_queue: SimpleQueue[dict] = SimpleQueue()
        self._solid_color_rgb: tuple[int, int, int] = (173, 216, 230)

        self._install_fallback(source="system", emit_event=True)
        self._load_default_script()

    # ------------------------------------------------------------------
    # Helpers
    def _install_fallback(self, *, source: str = "system", emit_event: bool = False):
        fallback = SolidColorAnimation(self.w, self.h, color=self._solid_color_rgb)
        if emit_event:
            self._set_animation(
                fallback,
                base_name="solid_color",
                label="solid_color",
                source=source,
                event_type="mode.changed",
                extra={"reason": "fallback"},
            )
        else:
            self.anim = fallback
            self.current_mode = "solid_color"
            self.current_mode_name = "solid_color"
        self.logger.info(f"Defaulting to solid color {self._solid_color_rgb}")

    def _set_animation(
        self,
        animation: Animation,
        *,
        base_name: str,
        label: str,
        source: str,
        event_type: str = "mode.changed",
        extra: dict | None = None,
    ) -> None:
        self.anim = animation
        self.current_mode_name = base_name
        self.current_mode = label
        if isinstance(animation, SolidColorAnimation):
            self._solid_color_rgb = tuple(int(c) for c in animation.color)
        if event_type:
            payload = {"mode": label, "base": base_name, "source": source}
            if extra:
                payload.update(extra)
            self.enqueue_event(event_type, **payload)

    def activate_mode(self, name: str, *, source: str = "ctrl", label: str | None = None) -> bool:
        name = (name or "").strip()
        if not name:
            self.enqueue_event("mode.error", message="No mode specified", source=source)
            self.logger.warning("Mode activation requested without a name")
            return False
        try:
            animation = create_animation(name, self.w, self.h)
        except Exception as exc:
            self.enqueue_event("mode.error", mode=name, message=str(exc), source=source)
            self.logger.error(f"Failed to activate mode '{name}': {exc}")
            return False
        if isinstance(animation, SolidColorAnimation):
            animation.set_color(self._solid_color_rgb)
        label = label or name
        self._set_animation(animation, base_name=name, label=label, source=source)
        return True

    def deactivate_mode(self, *, source: str = "ctrl") -> None:
        previous = self.current_mode or "?"
        self._install_fallback(source=source, emit_event=True)
        self.enqueue_event("mode.disabled", previous_mode=previous, source=source)

    def reset_mode(self, name: str | None = None, *, source: str = "ctrl") -> bool:
        target = (name or self.current_mode_name or "").strip()
        if not target:
            self.enqueue_event("mode.error", message="No mode available to reset", source=source)
            self.logger.warning("Reset requested without an active mode")
            return False
        self.enqueue_event("mode.reset", mode=target, source=source)
        if target.lower() == "solid_color":
            self._install_fallback(source=source, emit_event=True)
            return True
        return self.activate_mode(target, source=source)

    def _load_default_script(self):
        if not self.default_script:
            return
        self.logger.info(f"Loading default script: {self.default_script}")
        try:
            script_path = os.path.join(self.project_root, self.default_script)
            self.script = MscriptScript(script_path)
            self.enqueue_event("script.started", script=self.default_script, source="config")
            self.logger.info(f"Default script '{self.default_script}' loaded successfully.")
        except Exception as exc:
            self.enqueue_event("script.error", script=self.default_script, message=str(exc))
            self.logger.error(f"Failed to load default script '{self.default_script}': {exc}")

    # ------------------------------------------------------------------
    def enqueue_event(self, event_type: str, **data):
        payload = {
            "schema": "mochi.node.event.v1",
            "node_id": self.node_id,
            "event": event_type,
            "timestamp_ms": int(time.time() * 1000),
            "data": data,
        }
        self._event_queue.put(payload)

    def poll_event(self) -> dict | None:
        try:
            return self._event_queue.get_nowait()
        except Empty:
            return None

    def build_meta_payload(self) -> dict:
        payload = describe_node_catalog(self.topics, self.optional_topics)
        payload.update(
            {
                "timestamp_ms": int(time.time() * 1000),
                "logical_size": {"width": self.w, "height": self.h},
                "fps_target": self.fps,
                "addresses": {
                    "pub_frontend": self.pub_addr,
                    "pub_backend": self.pub_backend_addr,
                    "ctrl": self.ctrl_addr,
                },
            }
        )
        return payload

    def build_health_payload(self, seq: int, tx_rate_mbps: float, rss_bytes: int) -> dict:
        return {
            "schema": "mochi.node.health.v1",
            "node_id": self.node_id,
            "timestamp_ms": int(time.time() * 1000),
            "sequence": seq,
            "logical_size": {"width": self.w, "height": self.h},
            "fps_target": self.fps,
            "mode": self.current_mode or "?",
            "memory_mb": rss_bytes / (1024 * 1024),
            "tx_rate_mbps": tx_rate_mbps,
        }

    # ------------------------------------------------------------------
    def process_command(self, msg):
        """Process an incoming command from either ZMQ or a running script."""
        if isinstance(msg, Command):
            self._process_script_command(msg)
            return
        if not isinstance(msg, str):
            self.logger.warning(f"Ctrl: unsupported command type {type(msg)!r}")
            return

        parts = msg.strip().split()
        if not parts:
            return
        first = parts[0].lower()
        if first == "node":
            if len(parts) < 3:
                self.logger.warning(f"Ctrl: malformed node command: {msg}")
                return
            target_node = parts[1].lower()
            if target_node != self.node_id.lower():
                self.logger.debug("Ctrl: ignoring command for node '%s'", target_node)
                return
            parts = parts[2:]
        elif first == self.node_id.lower():
            parts = parts[1:]

        if not parts:
            self.logger.debug(f"Ctrl: no command after node prefix in '{msg}'")
            return
        cmd = parts[0].lower()
        self.logger.info(f"Ctrl: Received command: {msg}")

        try:
            if cmd == "mode":
                if len(parts) == 1:
                    self.logger.info(f"Ctrl: current mode -> {self.current_mode}")
                    return
                action = parts[1].lower()
                if action in {"on", "enable"}:
                    target = " ".join(parts[2:]) if len(parts) >= 3 else (self.current_mode_name or "")
                    if not target:
                        self.enqueue_event("mode.error", message="Mode on requested without a target", source="ctrl")
                        self.logger.warning("Mode on requested without a target")
                        return
                    self.activate_mode(target, source="ctrl")
                elif action in {"off", "disable"}:
                    self.deactivate_mode(source="ctrl")
                elif action == "reset":
                    target = " ".join(parts[2:]) if len(parts) >= 3 else None
                    self.reset_mode(target, source="ctrl")
                else:
                    name = " ".join(parts[1:])
                    self.activate_mode(name, source="ctrl")
            elif cmd == "size" and len(parts) == 2 and "x" in parts[1].lower():
                w_str, h_str = parts[1].lower().split("x", 1)
                new_w, new_h = int(w_str), int(h_str)
                self.w, self.h = new_w, new_h
                self.enqueue_event("size.changed", width=new_w, height=new_h, source="ctrl")
                self.logger.info(f"Ctrl: resized to {new_w}x{new_h}")
                if self.current_mode_name:
                    # Recreate the current mode with the new dimensions
                    label = self.current_mode or self.current_mode_name
                    self.activate_mode(self.current_mode_name, source="ctrl", label=label)
                else:
                    self._install_fallback(source="ctrl", emit_event=True)
            elif cmd == "color":
                color_args = parts[1:]
                target_mode = None

                def _is_int(val: str) -> bool:
                    try:
                        int(val)
                        return True
                    except ValueError:
                        return False

                if color_args and not _is_int(color_args[0]):
                    target_mode = color_args.pop(0).lower()
                if len(color_args) != 3:
                    self.enqueue_event("color.error", message="Color command expects three components", source="ctrl")
                    self.logger.warning(f"Ctrl: invalid color command args: {color_args}")
                    return
                try:
                    rgb = tuple(max(0, min(255, int(c))) for c in color_args)
                except ValueError:
                    self.enqueue_event("color.error", message="Color components must be integers", source="ctrl")
                    self.logger.warning(f"Ctrl: invalid color values: {color_args}")
                    return

                if target_mode in {"solid", "solid_color", "solidcolor", "fallback"}:
                    self._solid_color_rgb = rgb
                    if isinstance(self.anim, SolidColorAnimation):
                        self.anim.set_color(rgb)
                    self.enqueue_event("color.changed", rgb=rgb, target="solid_color", source="ctrl")
                    return

                if self.anim and hasattr(self.anim, "set_color"):
                    self.anim.set_color(rgb)
                    if isinstance(self.anim, SolidColorAnimation):
                        self._solid_color_rgb = rgb
                    self.enqueue_event("color.changed", rgb=rgb, source="ctrl")
                else:
                    self.logger.warning("Ctrl: color command ignored; current animation has no set_color")
            elif cmd == "play" and len(parts) >= 2:
                script_rel = " ".join(parts[1:])
                path = os.path.join(self.project_root, script_rel)
                self.script = MscriptScript(path)
                self.enqueue_event("script.started", script=script_rel, source="ctrl")
                self.logger.info(f"Ctrl: Started script '{path}'")
            elif cmd == "stop":
                if self.script:
                    self.logger.info("Ctrl: Script stopped by command")
                    self.enqueue_event("script.stopped", source="ctrl")
                    self.script = None
            else:
                self.enqueue_event("command.unknown", command=msg)
                self.logger.warning(f"Ctrl: unknown command: {msg}")
        except Exception as exc:
            self.enqueue_event("command.error", command=msg, message=str(exc))
            self.logger.error(f"CTRL parse error: {exc}")

    def _process_script_command(self, command: Command):
        """Handle structured commands emitted by an active script."""
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

        event_name = args.pop("EVENT", None)

        if event_name and key_int is not None:
            target_anim = self.keyframes.get(key_int)
            if not target_anim:
                self.logger.warning(f"Script: EVENT '{event_name}' for unknown key {key_int}")
                return
            try:
                payload_args = {k: v for k, v in args.items() if k != "K"}
                target_anim.on_event(event_name, **payload_args)
                self.anim = target_anim
                self.current_mode = f"{name}[{key_int}]"
                self.enqueue_event("animation.event", animation=self.current_mode, event=event_name, args=payload_args)
            except Exception as exc:
                self.enqueue_event("animation.error", animation=self.current_mode, message=str(exc))
                self.logger.error(f"Script: event '{event_name}' failed for key {key_int}: {exc}")
            return

        anim_kwargs = {k: v for k, v in args.items() if k != "K"}
        anim_kwargs["resolve_dir"] = self.project_root

        try:
            new_anim = create_animation(name, self.w, self.h, **anim_kwargs)
        except Exception as exc:
            self.enqueue_event("animation.error", animation=name, message=str(exc))
            self.logger.error(f"Script: failed to create animation '{name}' with args {anim_kwargs}: {exc}")
            return

        if key_int is not None:
            self.keyframes[key_int] = new_anim

        label = f"{name}[{key_int}]" if key_int is not None else name
        self._set_animation(new_anim, base_name=name, label=label, source="script")

    def update(self, timestamp):
        """Update the active script."""
        if self.script:
            due_commands = self.script.update(timestamp)
            for command in due_commands:
                self.process_command(command)

    def render(self, timestamp):
        """Render the current animation into a pixel buffer."""
        zmq_manager.ensure_buffers(self.w, self.h)
        try:
            self.anim.render_into(timestamp, zmq_manager.pixel_buf)
        except Exception as exc:
            self.enqueue_event("frame.error", animation=self.current_mode, message=str(exc))
            self.logger.error(f"frame() error from '{self.current_mode}': {exc}")
            error_color_bytes = b"\x80\x00\x00"
            zmq_manager.pixel_buf[:] = error_color_bytes * (self.w * self.h)
        return zmq_manager.pixel_buf

class SolidColorAnimation(Animation):
    """A simple fallback animation that fills the screen with a solid color."""
    def __init__(self, w, h, color=(0, 0, 0)):
        super().__init__(w, h)
        self.set_color(color)

    def render_into(self, t: float, pixel_buf: bytearray):
        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        frame[:, :] = self.color

    def set_color(self, color: tuple[int, int, int] | list[int]):
        self.color = tuple(max(0, min(255, int(c))) for c in color)

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

    config = config or {}
    env_cfg_raw = os.environ.get("MOCHI_PLUGIN_CONFIG_JSON")
    if env_cfg_raw:
        try:
            env_cfg = json.loads(env_cfg_raw)
            if isinstance(env_cfg, dict):
                config = _merge_dicts(config, env_cfg)
        except json.JSONDecodeError as exc:
            logger.warning(f"Invalid MOCHI_PLUGIN_CONFIG_JSON: {exc}")

    node_config = config.get("node", {})

    node_id = os.environ.get("MOCHI_NODE_ID") or node_config.get("id") or "animation"

    optional_topics_cfg = node_config.get("optional_topics", []) or []
    optional_topics_env = os.environ.get("MOCHI_NODE_OPTIONAL_TOPICS", "")
    if optional_topics_env:
        optional_topics_cfg = list(optional_topics_cfg) + [t.strip() for t in optional_topics_env.split(",") if t.strip()]
    optional_topics: list[bytes] = []
    for entry in optional_topics_cfg:
        if isinstance(entry, bytes):
            optional_topics.append(entry)
        elif isinstance(entry, str):
            optional_topics.append(entry.encode("utf-8"))
        else:
            logger.warning(f"Ignoring optional topic with unsupported type: {entry!r}")

    if optional_topics:
        optional_topics = list(dict.fromkeys(optional_topics))

    node = AnimationNode(node_id, node_config, PLUGIN_ROOT, optional_topics=optional_topics)

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
    meta_payload = node.build_meta_payload()
    pub.send_multipart([node.topics.meta, json.dumps(meta_payload).encode("utf-8")])
    logger.info(
        "Publisher ready; logical_size=%dx%d; FPS=%s; meta=%s",
        node.w,
        node.h,
        node.fps,
        node.topics.meta.decode("utf-8"),
    )

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
            pub.send_multipart([node.topics.frame, packed_bytes], copy=False)
            bytes_sent_since_health += len(packed_bytes)

            # Flush any pending event payloads
            while True:
                event_payload = node.poll_event()
                if not event_payload:
                    break
                pub.send_multipart([node.topics.event, json.dumps(event_payload).encode("utf-8")])

            now_wall = time.time()
            if now_wall - last_health_t >= 1.0:
                mem_info = process.memory_info()
                elapsed = max(1e-6, now_wall - last_health_t)
                tx_rate_mbps = (bytes_sent_since_health / elapsed) / (1024 * 1024)
                hb = node.build_health_payload(seq, tx_rate_mbps, mem_info.rss)
                pub.send_multipart([node.topics.health, json.dumps(hb).encode("utf-8")])
                last_health_t = now_wall
                bytes_sent_since_health = 0

            seq += 1
            next_frame += dt
    finally:
        shutdown_evt.set()
        node.enqueue_event("node.stopping", reason="shutdown")
        try:
            while True:
                pending = node.poll_event()
                if not pending:
                    break
                pub.send_multipart([node.topics.event, json.dumps(pending).encode("utf-8")])
        except Exception:
            pass

        logger.info("Shutting down plugin.")
        try:
            pub.close()
            ctx.term()
        except Exception as e:
            logger.error(f"Error during ZMQ shutdown: {e}")

if __name__ == "__main__":
    main()
