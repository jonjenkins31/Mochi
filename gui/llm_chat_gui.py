"""
Simple Tk chat client for interacting with the Mochi LLM node.

Reads addresses/topics from the main config files, publishes user text onto the
configured STT topic, and subscribes to LLM reply topics to display responses.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Any, Iterable

import sys

import yaml
import zmq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND = "tcp://127.0.0.1:5555"
DEFAULT_BACKEND = "tcp://127.0.0.1:5557"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.messages import Msg, build, TOPIC_STT_TEXT, TOPIC_LLM_REPLY

CONFIG_PATHS = [
    PROJECT_ROOT / "config.yaml",
    PROJECT_ROOT / "plugins" / "llm_node" / "config.yaml",
]


def _merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_combined_config() -> dict[str, Any]:
    combined: dict[str, Any] = {}
    for path in CONFIG_PATHS:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if isinstance(data, dict):
                combined = _merge_dicts(combined, data)
        except yaml.YAMLError as exc:
            print(f"[llm-gui] Warning: cannot parse {path}: {exc}")
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"[llm-gui] Warning: cannot read {path}: {exc}")
    return combined


def _as_topic_bytes(values: Iterable[str] | None, *, defaults: Iterable[bytes]) -> list[bytes]:
    topics: list[bytes] = []
    for entry in values or ():
        if isinstance(entry, bytes):
            candidate = entry
        else:
            candidate = str(entry).encode("utf-8")
        candidate = candidate.strip()
        if candidate:
            topics.append(candidate)
    if not topics:
        topics.extend(defaults)
    # Deduplicate while preserving order
    seen: set[bytes] = set()
    deduped: list[bytes] = []
    for topic in topics:
        if topic not in seen:
            deduped.append(topic)
            seen.add(topic)
    return deduped


class LLMChatGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Mochi LLM Chat")

        self.config = _load_combined_config()
        self._setup_addresses()

        self.ctx = zmq.Context.instance()
        self.pub_socket = None
        self.sub_socket = None
        self._listener_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()

        self._build_ui()
        self._connect_sockets()
        self._start_listener()
        self._drain_queue()

    # ------------------------------------------------------------------ setup helpers
    def _setup_addresses(self):
        broker_cfg = self.config.get("broker", {}) or {}
        node_cfg = self.config.get("node", {}) or {}

        llm_section = self.config.get("llm") or {}
        if isinstance(llm_section, dict):
            llm_node_cfg = llm_section.get("node", {}) or llm_section
        else:
            llm_node_cfg = {}

        self.frontend_addr = str(
            broker_cfg.get("frontend_addr")
            or node_cfg.get("pub_address")
            or DEFAULT_FRONTEND
        )
        self.backend_addr = str(
            broker_cfg.get("backend_addr")
            or node_cfg.get("pub_backend_address")
            or DEFAULT_BACKEND
        )

        publish_topics = _as_topic_bytes(
            llm_node_cfg.get("publish_topics") if isinstance(llm_node_cfg, dict) else None,
            defaults=(TOPIC_LLM_REPLY,),
        )
        subscribe_topics = _as_topic_bytes(
            llm_node_cfg.get("subscribe_topics") if isinstance(llm_node_cfg, dict) else None,
            defaults=(TOPIC_STT_TEXT,),
        )
        self.reply_topics = publish_topics
        self.stt_topic = subscribe_topics[0] if subscribe_topics else TOPIC_STT_TEXT
        self.source_label = llm_node_cfg.get("source_label", "llm-gui")

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        info = ttk.Label(
            main,
            text=f"PUB → {self.stt_topic.decode('utf-8')} @ {self.backend_addr}\n"
                 f"SUB ← {[t.decode('utf-8') for t in self.reply_topics]} @ {self.frontend_addr}",
            justify=tk.LEFT,
        )
        info.grid(row=0, column=0, sticky="ew")

        self.log_box = tk.Text(main, height=18, wrap=tk.WORD, state=tk.DISABLED)
        self.log_box.grid(row=1, column=0, sticky="nsew", pady=(8, 8))

        input_frame = ttk.Frame(main)
        input_frame.grid(row=2, column=0, sticky="ew")
        input_frame.columnconfigure(0, weight=1)

        self.entry = tk.Text(input_frame, height=3, wrap=tk.WORD)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        send_btn = ttk.Button(input_frame, text="Send", command=self._on_send)
        send_btn.grid(row=0, column=1, sticky="e")

        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Shift-Return>", lambda event: None)
        self.entry.focus_set()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _connect_sockets(self):
        self.pub_socket = self.ctx.socket(zmq.PUB)
        self.pub_socket.setsockopt(zmq.LINGER, 0)
        self.pub_socket.connect(self.backend_addr)
        # Give downstream subscribers a moment to connect
        time.sleep(0.05)

        self.sub_socket = self.ctx.socket(zmq.SUB)
        self.sub_socket.setsockopt(zmq.LINGER, 0)
        self.sub_socket.connect(self.frontend_addr)
        for topic in self.reply_topics:
            self.sub_socket.setsockopt(zmq.SUBSCRIBE, topic)

    def _start_listener(self):
        self._listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
        self._listener_thread.start()

    # ------------------------------------------------------------------ UI handlers
    def _append_message(self, speaker: str, text: str):
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.insert(tk.END, f"{speaker}: {text.strip()}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _on_send(self):
        text = self.entry.get("1.0", tk.END).strip()
        if not text:
            return

        try:
            msg = build(source=self.source_label, kind="user", text=text)
            payload = msg.to_json()
            self.pub_socket.send_multipart([self.stt_topic, payload])
            self._append_message("You", text)
        except Exception as exc:  # pragma: no cover - runtime guard
            messagebox.showerror("Send failed", str(exc))
            return
        finally:
            self.entry.delete("1.0", tk.END)

    def _on_return(self, event):
        if event.state & 0x0001:  # Shift pressed
            return
        self._on_send()
        return "break"

    # ------------------------------------------------------------------ background loop
    def _listener_loop(self):
        while not self._stop_event.is_set():
            if self.sub_socket is None:
                break
            try:
                topic, payload = self.sub_socket.recv_multipart(flags=zmq.NOBLOCK)
            except zmq.Again:
                time.sleep(0.05)
                continue
            except Exception:
                break

            try:
                msg = Msg.from_json(payload)
                text = msg.text
            except Exception:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    text = data.get("text", "")
                except Exception:
                    text = payload.decode("utf-8", errors="ignore")

            label = topic.decode("utf-8", errors="ignore")
            self._queue.put((label, text))

    def _drain_queue(self):
        while True:
            try:
                topic, text = self._queue.get_nowait()
            except queue.Empty:
                break
            self._append_message(topic, text)
        self.root.after(100, self._drain_queue)

    # ------------------------------------------------------------------ cleanup
    def _on_close(self):
        self._stop_event.set()
        self.root.after(100, self._finalize_shutdown)

    def _finalize_shutdown(self):
        if self._listener_thread and self._listener_thread.is_alive():
            self.root.after(100, self._finalize_shutdown)
            return
        self._close_sockets()
        self.root.destroy()

    def _close_sockets(self):
        if self.sub_socket is not None:
            self.sub_socket.close(0)
            self.sub_socket = None
        if self.pub_socket is not None:
            self.pub_socket.close(0)
            self.pub_socket = None


def main():
    root = tk.Tk()
    LLMChatGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
