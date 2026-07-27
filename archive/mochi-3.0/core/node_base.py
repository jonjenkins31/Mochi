"""
core/node_base.py
-----------------

Provides MochiNodeBase, a reusable base class for all Mochi plugins.
It encapsulates the common boilerplate for:
- ZMQ socket setup (PUB for data/events, PULL for commands).
- Main run loop with FPS timing and graceful shutdown.
- Health and metadata publishing.
- A generic event queue.
- Command parsing for multi-node environments.

To create a new plugin, inherit from this class and implement the abstract
methods for your plugin's specific logic.
"""

import abc
import json
import logging
import os
import signal
import threading
import time
from queue import Empty, SimpleQueue
from typing import Any, Sequence

import psutil
import zmq

from . import describe_node_catalog, make_node_topics
from . import zmq_manager as core_zmq_manager


class MochiNodeBase(abc.ABC):
    """Abstract base class for a Mochi plugin node."""

    def __init__(
        self,
        node_id: str,
        config: dict,
        project_root: str,
        optional_topics: Sequence[bytes] | None = None,
    ):
        self.node_id = node_id
        self.project_root = project_root
        self.config = config
        self.topics = make_node_topics(node_id)
        self.optional_topics = tuple(optional_topics or ())
        self.logger = logging.getLogger(f"MochiNode[{self.node_id}]")

        # --- Config & Transport ---
        self.fps = self.config.get("fps", 60)
        env = os.environ
        self.pub_addr = env.get("MOCHI_BROKER_XPUB", self.config.get("pub_address", "tcp://127.0.0.1:5555"))
        self.pub_backend_addr = env.get("MOCHI_BROKER_XSUB", self.config.get("pub_backend_address"))
        self.ctrl_addr = env.get("MOCHI_NODE_CTRL_ADDR", self.config.get("ctrl_address", "tcp://127.0.0.1:5556"))

        # --- State ---
        self._event_queue: SimpleQueue[dict] = SimpleQueue()
        self._shutdown_evt = threading.Event()
        self._process = psutil.Process(os.getpid())

        # --- ZMQ ---
        self._ctx = zmq.Context.instance()
        self._pub_socket: zmq.Socket | None = None

    # ------------------------------------------------------------------
    # Public API for subclasses
    # ------------------------------------------------------------------

    def enqueue_event(self, event_type: str, **data: Any) -> None:
        """Queue a structured event for publishing."""
        payload = {
            "schema": "mochi.node.event.v1",
            "node_id": self.node_id,
            "event": event_type,
            "timestamp_ms": int(time.time() * 1000),
            "data": data,
        }
        self._event_queue.put(payload)

    # ------------------------------------------------------------------
    # Abstract methods for subclass implementation
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def _update_tick(self, timestamp: float) -> None:
        """
        Called on each frame to update the node's internal state.
        This is where to process scripts, state machines, etc.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def _render_tick(self, timestamp: float) -> memoryview | None:
        """
        Called on each frame to render the output.
        Should return a memoryview of the raw pixel buffer (e.g., RGB888).
        If None is returned, no frame is published.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def _process_node_command(self, command: str, parts: list[str]) -> None:
        """
        Process a command specifically for this node. The `node <id>` prefix
        will have already been stripped.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_health_details(self) -> dict:
        """Return a dictionary of node-specific health details."""
        return {}

    @abc.abstractmethod
    def get_meta_details(self) -> dict:
        """Return a dictionary of node-specific metadata."""
        return {}

    @abc.abstractmethod
    def on_shutdown(self) -> None:
        """Perform any custom cleanup before the node terminates."""
        pass

    # ------------------------------------------------------------------
    # Core run loop and infrastructure
    # ------------------------------------------------------------------

    def _sig_handler(self, _s: Any, _f: Any) -> None:
        self.logger.info("Shutdown signal received.")
        self._shutdown_evt.set()

    def _control_loop(self) -> None:
        """The thread that listens for and processes incoming commands."""
        pull_socket = self._ctx.socket(zmq.PULL)
        pull_socket.bind(self.ctrl_addr)
        self.logger.info(f"Control socket listening (PULL) -> {self.ctrl_addr}")
        try:
            while not self._shutdown_evt.is_set():
                try:
                    msg = pull_socket.recv_string(flags=zmq.NOBLOCK)
                    if msg.strip().lower() == "quit":
                        self.logger.info("Ctrl: 'quit' received")
                        self._shutdown_evt.set()
                        break

                    command_parts = self._parse_node_prefix(msg.strip().split())
                    if command_parts is not None:  # Command is for this node
                        self._process_node_command(msg, command_parts)

                except zmq.Again:
                    time.sleep(0.05)
                except Exception as e:
                    if self._shutdown_evt.is_set():
                        break
                    self.logger.error(f"Error in control loop: {e}", exc_info=True)
        finally:
            pull_socket.close(linger=0)

    def _parse_node_prefix(self, parts: list[str]) -> list[str] | None:
        """
        Checks for and consumes a `node <id>` or `<id>` prefix.
        Returns the remaining command parts if the command is for this node,
        otherwise returns None.
        """
        if not parts:
            return []
        first = parts[0].lower()
        if first == "node":
            if len(parts) < 3:
                self.logger.warning(f"Ctrl: malformed node command: {' '.join(parts)}")
                return None
            if parts[1].lower() != self.node_id.lower():
                return None  # Ignore, for another node
            return parts[2:]
        if first == self.node_id.lower():
            return parts[1:]
        return parts  # No prefix, assume it's for us

    def _publish_events(self) -> None:
        """Publish all queued events."""
        if not self._pub_socket:
            return
        while True:
            try:
                payload = self._event_queue.get_nowait()
                self._pub_socket.send_multipart([self.topics.event, json.dumps(payload).encode("utf-8")])
            except Empty:
                break

    def _build_meta_payload(self) -> dict:
        payload = describe_node_catalog(self.topics, self.optional_topics)
        payload.update({
            "timestamp_ms": int(time.time() * 1000),
            "addresses": {
                "pub_frontend": self.pub_addr,
                "pub_backend": self.pub_backend_addr,
                "ctrl": self.ctrl_addr,
            },
        })
        payload.update(self.get_meta_details())
        return payload

    def _build_health_payload(self, seq: int, tx_rate_mbps: float) -> dict:
        mem_info = self._process.memory_info()
        payload = {
            "schema": "mochi.node.health.v1",
            "node_id": self.node_id,
            "timestamp_ms": int(time.time() * 1000),
            "sequence": seq,
            "fps_target": self.fps,
            "memory_mb": mem_info.rss / (1024 * 1024),
            "tx_rate_mbps": tx_rate_mbps,
        }
        payload.update(self.get_health_details())
        return payload

    def run(self) -> None:
        """Start the node and enter the main run loop."""
        signal.signal(signal.SIGINT, self._sig_handler)
        signal.signal(signal.SIGTERM, self._sig_handler)

        # --- Start control thread ---
        threading.Thread(target=self._control_loop, daemon=True).start()

        # --- Setup publisher ---
        self._pub_socket = self._ctx.socket(zmq.PUB)
        self._pub_socket.setsockopt(zmq.LINGER, 0)
        self._pub_socket.setsockopt(zmq.SNDHWM, 2)
        if self.pub_backend_addr:
            self._pub_socket.connect(self.pub_backend_addr)
        else:
            self._pub_socket.bind(self.pub_addr)
        time.sleep(0.1)  # Allow connections

        # --- Announce presence ---
        meta_payload = self._build_meta_payload()
        self._pub_socket.send_multipart([self.topics.meta, json.dumps(meta_payload).encode("utf-8")])
        self.logger.info("Node is online. Meta payload sent.")

        # --- Main render loop ---
        seq = 0
        clock = time.perf_counter
        dt = 1.0 / float(self.fps) if self.fps > 0 else 0.01
        next_frame_time = clock()
        last_health_time = 0.0
        bytes_sent_since_health = 0

        try:
            while not self._shutdown_evt.is_set():
                now = clock()
                if now < next_frame_time:
                    time.sleep(max(0.0, next_frame_time - now))

                self._update_tick(time.time())
                rendered_pixels = self._render_tick(time.time())

                if rendered_pixels:
                    w, h = self.get_health_details().get("logical_size", {}).get("width", 0), self.get_health_details().get("logical_size", {}).get("height", 0)
                    packed_bytes = core_zmq_manager.pack_frame(w, h, seq, rendered_pixels)
                    self._pub_socket.send_multipart([self.topics.frame, packed_bytes], copy=False)
                    bytes_sent_since_health += len(packed_bytes)

                self._publish_events()

                now_wall = time.time()
                if now_wall - last_health_time >= 1.0:
                    elapsed = max(1e-6, now_wall - last_health_time)
                    tx_rate_mbps = (bytes_sent_since_health / elapsed) / (1024 * 1024)
                    hb = self._build_health_payload(seq, tx_rate_mbps)
                    self._pub_socket.send_multipart([self.topics.health, json.dumps(hb).encode("utf-8")])
                    last_health_time = now_wall
                    bytes_sent_since_health = 0

                seq += 1
                next_frame_time += dt
        finally:
            self.logger.info("Shutting down...")
            self.on_shutdown()
            self.enqueue_event("node.stopping", reason="shutdown")
            self._publish_events()
            if self._pub_socket:
                self._pub_socket.close(0)
            self._ctx.term()
            self.logger.info("Shutdown complete.")