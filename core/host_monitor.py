"""Host-side aggregator that caches health/event updates for tooling."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import zmq


@dataclass
class NodeState:
    health: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    last_event: dict = field(default_factory=dict)


class HostMonitor:
    """Subscribes to broker topics and exposes a REP socket for queries."""

    def __init__(self, frontend_addr: str, rep_addr: str):
        self.frontend_addr = frontend_addr
        self.rep_addr = rep_addr
        self.ctx = zmq.Context.instance()
        self.state: Dict[str, NodeState] = {}
        self._stop = threading.Event()
        self._sub_thread = threading.Thread(target=self._sub_loop, daemon=True)
        self._rep_thread = threading.Thread(target=self._rep_loop, daemon=True)

    def start(self) -> None:
        self._sub_thread.start()
        self._rep_thread.start()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        self._sub_thread.join(timeout)
        self._rep_thread.join(timeout)

    def _sub_loop(self) -> None:
        sub = self.ctx.socket(zmq.SUB)
        sub.setsockopt(zmq.RCVHWM, 10)
        sub.connect(self.frontend_addr)
        sub.setsockopt(zmq.SUBSCRIBE, b"node.")
        poller = zmq.Poller()
        poller.register(sub, zmq.POLLIN)
        while not self._stop.is_set():
            socks = dict(poller.poll(timeout=250))
            if sub not in socks or socks[sub] != zmq.POLLIN:
                continue
            try:
                topic, payload = sub.recv_multipart()
            except zmq.error.ZMQError:
                if self._stop.is_set():
                    break
                continue
            try:
                data = json.loads(payload.decode("utf-8")) if payload else {}
            except json.JSONDecodeError:
                continue
            topic_str = topic.decode("utf-8")
            parts = topic_str.split(".")
            if len(parts) < 3:
                continue
            _, node_id, signal = parts[0], parts[1], parts[2]
            node_state = self.state.setdefault(node_id, NodeState())
            if signal == "health":
                node_state.health = data
            elif signal == "meta":
                node_state.meta = data
            elif signal == "event":
                node_state.last_event = data

        sub.close(0)

    def _rep_loop(self) -> None:
        rep = self.ctx.socket(zmq.REP)
        rep.bind(self.rep_addr)
        poller = zmq.Poller()
        poller.register(rep, zmq.POLLIN)
        while not self._stop.is_set():
            socks = dict(poller.poll(timeout=250))
            if rep not in socks or socks[rep] != zmq.POLLIN:
                continue
            try:
                request = rep.recv_string()
            except zmq.error.ZMQError:
                if self._stop.is_set():
                    break
                continue
            reply = self._handle_request(request)
            rep.send_string(reply)
        rep.close(0)

    def _handle_request(self, request: str) -> str:
        parts = request.strip().split()
        if not parts:
            return json.dumps({"error": "empty request"})
        cmd = parts[0].upper()
        if cmd == "GET":
            scope = parts[1].lower() if len(parts) >= 2 else "health"
            node_id = parts[2] if len(parts) >= 3 else None
            if node_id:
                node = self.state.get(node_id)
                if not node:
                    return json.dumps({"error": f"unknown node {node_id}"})
                payload = getattr(node, scope, None)
                if payload is None:
                    return json.dumps({"error": f"unknown scope {scope}"})
                return json.dumps(payload)
            else:
                if scope == "health":
                    return json.dumps({nid: ns.health for nid, ns in self.state.items()})
                if scope == "meta":
                    return json.dumps({nid: ns.meta for nid, ns in self.state.items()})
                if scope == "event":
                    return json.dumps({nid: ns.last_event for nid, ns in self.state.items()})
                return json.dumps({"error": f"unknown scope {scope}"})
        return json.dumps({"error": f"unknown command {request}"})
