"""Shared health subscriber for the Mochi companion.

Phase 1 of the Tk → companion migration (see
docs/SUPERSEDE_TK_PLAN.md).  Extracts the ``_health_poll_loop`` +
``_process_health_queue`` pattern from gui/mochi_gui.py into a
reusable Qt-friendly service.

Usage:

    health = HealthService()
    health.health_updated.connect(on_health)
    health.start()
    ...
    health.stop()

``on_health`` receives ``(node_id: str, payload: dict)`` per
broadcast.  ``health.snapshot(node_id)`` returns the most recent
payload, or ``None`` if no health has arrived for that node.

Lifecycle:
  - SUB socket connects to the broker on ``health_sub_addr`` (default
    ``tcp://127.0.0.1:5555``)
  - Subscribes to the ``node.`` topic prefix
  - Background thread polls non-blocking, pushes messages onto a
    queue
  - A QTimer in the main thread drains the queue and emits the
    signal (so consumers stay on the Qt event loop)

This mirrors the Tk panel's pattern but uses Qt signals instead of
Tk's ``after()`` callbacks, and uses a thread-safe dict snapshot
so multiple consumers can read state without each maintaining
their own subscriber.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from queue import Empty, Queue

import zmq
from PySide6.QtCore import QObject, Signal, QTimer


DEFAULT_HEALTH_ADDR = "tcp://127.0.0.1:5555"
HEALTH_TOPIC_PREFIX = b"node."


class HealthService(QObject):
    """Background ZMQ SUB listener that fans health broadcasts out to
    Qt consumers via signals.

    Signals
    -------
    health_updated(node_id, payload)
        Fired on every health-shaped message.  ``node_id`` derived
        from the broadcast topic; ``payload`` is the parsed JSON
        dict.

    event_received(node_id, payload)
        Fired for non-health messages (``.event`` / ``.meta``) that
        arrive on the same ``node.`` prefix.

    error(message)
        Fired when the SUB socket can't connect or decode payload.

    Properties
    ----------
    snapshot(node_id) → dict | None
        Latest payload for ``node_id``.  ``None`` until first
        broadcast arrives.

    all_snapshots() → dict[str, dict]
        Copy of every known node's latest payload.

    last_seen(node_id) → float | None
        Monotonic timestamp of the last broadcast (lets the UI fade
        "stale" status pills to grey after N seconds).
    """

    health_updated = Signal(str, dict)
    event_received = Signal(str, dict)
    error = Signal(str)

    def __init__(
        self,
        *,
        health_sub_addr: str = DEFAULT_HEALTH_ADDR,
        poll_interval_ms: int = 100,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__()
        self._addr = health_sub_addr
        self._poll_ms = poll_interval_ms
        self._logger = logger or logging.getLogger("HealthService")

        self._ctx = zmq.Context.instance()
        self._sub: zmq.Socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._queue: Queue = Queue()

        self._snapshots: dict[str, dict] = {}
        self._last_seen: dict[str, float] = {}
        self._lock = threading.Lock()

        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(self._poll_ms)
        self._drain_timer.timeout.connect(self._drain_queue)

    # ── lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return  # already running
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._sub_loop, daemon=True,
        )
        self._thread.start()
        self._drain_timer.start()
        self._logger.info("HealthService started — %s", self._addr)

    def stop(self) -> None:
        # The SUB socket is created, used, and closed on the worker
        # thread only (see _sub_loop's finally) — closing it here
        # while the worker may be inside recv_multipart is unsafe.
        self._stop.set()
        self._drain_timer.stop()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._logger.info("HealthService stopped")

    # ── snapshot accessors ────────────────────────────────────────

    def snapshot(self, node_id: str) -> dict | None:
        with self._lock:
            data = self._snapshots.get(node_id)
            return dict(data) if data is not None else None

    def all_snapshots(self) -> dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._snapshots.items()}

    def last_seen(self, node_id: str) -> float | None:
        with self._lock:
            return self._last_seen.get(node_id)

    def known_nodes(self) -> list[str]:
        with self._lock:
            return sorted(self._snapshots.keys())

    # ── internal: SUB thread ─────────────────────────────────────

    def _sub_loop(self) -> None:
        # The SUB socket lives entirely on this thread — created
        # here, used here, closed in the ``finally`` below.  stop()
        # only sets the event and joins; it never touches the socket.
        try:
            try:
                self._sub = self._ctx.socket(zmq.SUB)
                self._sub.setsockopt(zmq.RCVHWM, 1)
                self._sub.setsockopt(zmq.SUBSCRIBE, HEALTH_TOPIC_PREFIX)
                self._sub.connect(self._addr)
                self._logger.info(
                    "SUB connected — addr=%s prefix=%s",
                    self._addr,
                    HEALTH_TOPIC_PREFIX.decode("utf-8", errors="ignore"),
                )
            except Exception as exc:  # noqa: BLE001
                self._logger.error("SUB connect failed: %s", exc)
                self._queue.put(
                    ("__error__", {"error": str(exc)}, False)
                )
                return

            while not self._stop.is_set():
                try:
                    topic, payload = self._sub.recv_multipart(
                        flags=zmq.NOBLOCK,
                    )
                except zmq.Again:
                    time.sleep(0.1)
                    continue
                except Exception as exc:  # noqa: BLE001
                    if not self._stop.is_set():
                        self._logger.warning(
                            "SUB recv error: %s", exc,
                        )
                    continue

                # Topic shape: ``node.<id>.health`` (or similar)
                try:
                    topic_str = topic.decode("utf-8", errors="ignore")
                    parts = topic_str.split(".")
                    node_id = parts[1] if len(parts) >= 2 else "unknown"
                    data = json.loads(payload.decode("utf-8"))
                except Exception as exc:  # noqa: BLE001
                    self._logger.warning(
                        "malformed health payload: %s", exc,
                    )
                    continue

                # Only ``.health`` messages drive the snapshot and the
                # health_updated signal; ``.event`` / ``.meta`` arrive
                # on the same prefix but carry different shapes, so
                # they fan out via event_received instead.
                is_health = (
                    len(parts) >= 3 and parts[2] == "health"
                ) or "mode" in data or "logical_size" in data

                if is_health:
                    with self._lock:
                        self._snapshots[node_id] = data
                        self._last_seen[node_id] = time.monotonic()

                self._queue.put((node_id, data, is_health))
        finally:
            if self._sub is not None:
                try:
                    self._sub.close(linger=0)
                except Exception:  # noqa: BLE001
                    pass
            self._sub = None

    # ── main-thread: queue drain ─────────────────────────────────

    def _drain_queue(self) -> None:
        try:
            while True:
                node_id, data, is_health = self._queue.get_nowait()
                if node_id == "__error__":
                    self.error.emit(data.get("error", "unknown error"))
                    continue
                if is_health:
                    self.health_updated.emit(node_id, data)
                else:
                    self.event_received.emit(node_id, data)
        except Empty:
            return


# ── convenience helpers for consumers ─────────────────────────────

def format_status_pill(snapshot: dict | None) -> str:
    """Render a snapshot as a compact one-line summary suitable for
    a top-toolbar status pill.

    ``snapshot`` is whatever ``HealthService.snapshot(node)`` returns.
    """
    if not snapshot:
        return "no data"

    mode = (
        snapshot.get("mode")
        or snapshot.get("data", {}).get("mode")
        or "?"
    )
    size_block = snapshot.get("logical_size") or {}
    w = size_block.get("width", snapshot.get("w", "?"))
    h = size_block.get("height", snapshot.get("h", "?"))
    fps = snapshot.get("fps_target", snapshot.get("fps", 0))
    mem = snapshot.get("memory_mb", snapshot.get("mem_mb", 0.0))

    return f"{mode} · {w}×{h} · {fps}fps · {mem:.1f}MB"


def staleness(last_seen: float | None) -> str:
    """Return ``'fresh'`` / ``'stale'`` / ``'gone'`` based on how
    recently the snapshot updated."""
    if last_seen is None:
        return "gone"
    age = time.monotonic() - last_seen
    if age < 5.0:
        return "fresh"
    if age < 30.0:
        return "stale"
    return "gone"
