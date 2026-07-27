"""
Simple Qt chat client for interacting with the Mochi LLM node.

Reads addresses/topics from the main config files, publishes user text onto the
configured STT topic, and subscribes to LLM reply topics to display responses.

PySide6 port of the original tkinter client: only the widget/layout/event-loop
layer changed. The zmq messaging, listener thread, queue draining and overall
behavior are identical to the tk version.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import sys

import yaml
import zmq

from PySide6.QtCore import Qt, QObject, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRONTEND = "tcp://127.0.0.1:5555"
DEFAULT_BACKEND = "tcp://127.0.0.1:5557"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from transport.messages import Msg, build, TOPIC_STT_TEXT, TOPIC_LLM_REPLY

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


class _ChatEntry(QTextEdit):
    """Multi-line input that sends on <Return> and inserts a newline on <Shift+Return>.

    Mirrors the tk behavior where <Return> triggers send and <Shift-Return> is a
    plain newline.
    """

    returnPressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            self.returnPressed.emit()
            return
        super().keyPressEvent(event)


class LLMChatGUI(QMainWindow):
    # Marshals (topic, text) tuples from the listener thread onto the UI thread.
    _message_received = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mochi LLM Chat")

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
        infra_cfg = self.config.get("infrastructure", {}) or {}
        broker_cfg = infra_cfg.get("broker") or self.config.get("broker") or {}
        node_cfg = self.config.get("node", {}) or {}
        llm_node_cfg = node_cfg
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
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)

        info = QLabel(
            f"PUB → {self.stt_topic.decode('utf-8')} @ {self.backend_addr}\n"
            f"SUB ← {[t.decode('utf-8') for t in self.reply_topics]} @ {self.frontend_addr}",
            central,
        )
        info.setAlignment(Qt.AlignLeft)
        layout.addWidget(info)

        self.log_box = QTextEdit(central)
        self.log_box.setReadOnly(True)
        self.log_box.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.log_box, stretch=1)

        input_frame = QWidget(central)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)

        self.entry = _ChatEntry(input_frame)
        self.entry.setLineWrapMode(QTextEdit.WidgetWidth)
        # ~3 text lines tall, matching the tk height=3 input box.
        self.entry.setFixedHeight(3 * self.entry.fontMetrics().lineSpacing() + 12)
        input_layout.addWidget(self.entry, stretch=1)

        send_btn = QPushButton("Send", input_frame)
        input_layout.addWidget(send_btn, alignment=Qt.AlignRight)

        layout.addWidget(input_frame)

        send_btn.clicked.connect(self._on_send)
        self.entry.returnPressed.connect(self._on_send)
        self._message_received.connect(self._append_message)
        self.entry.setFocus()

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
        self.log_box.append(f"{speaker}: {text.strip()}")
        scrollbar = self.log_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_send(self):
        text = self.entry.toPlainText().strip()
        if not text:
            return

        try:
            msg = build(source=self.source_label, kind="user", text=text)
            payload = msg.to_json()
            self.pub_socket.send_multipart([self.stt_topic, payload])
            self._append_message("You", text)
        except Exception as exc:  # pragma: no cover - runtime guard
            QMessageBox.critical(self, "Send failed", str(exc))
            return
        finally:
            self.entry.clear()

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
            self._message_received.emit(topic, text)
        QTimer.singleShot(100, self._drain_queue)

    # ------------------------------------------------------------------ cleanup
    def closeEvent(self, event):
        self._stop_event.set()
        self._finalize_shutdown(event)

    def _finalize_shutdown(self, event):
        if self._listener_thread and self._listener_thread.is_alive():
            event.ignore()
            QTimer.singleShot(100, lambda: self._retry_close())
            return
        self._close_sockets()
        event.accept()

    def _retry_close(self):
        # Re-issue a close now that the listener thread should have exited.
        self.close()

    def _close_sockets(self):
        if self.sub_socket is not None:
            self.sub_socket.close(0)
            self.sub_socket = None
        if self.pub_socket is not None:
            self.pub_socket.close(0)
            self.pub_socket = None


def main(argv=None) -> int:
    app = QApplication.instance() or QApplication(sys.argv if argv is None else argv)
    win = LLMChatGUI()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
