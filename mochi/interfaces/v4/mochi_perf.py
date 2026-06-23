# mochi_perf.py
# A simple performance and health monitor for a Mochi node.

import json
import logging
import sys
from pathlib import Path

import yaml
import zmq

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QWidget,
)

# --- Constants ---
# The root directory of the Mochi project.
GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
CONFIG_PATHS = [
    PROJECT_ROOT / "config.yaml",
    PROJECT_ROOT / "plugins" / "animation_node" / "config.yaml",
]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from transport import make_node_topics


def _load_perf_settings(logger):
    settings = {}
    for path in CONFIG_PATHS:
        try:
            with path.open("r", encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            continue
        except yaml.YAMLError as exc:
            logger.warning(f"Cannot parse {path}: {exc}")
            continue
        except Exception as exc:
            logger.warning(f"Cannot read {path}: {exc}")
            continue

        node_cfg = cfg.get("node") or {}
        display_cfg = cfg.get("display") or {}
        if "pub_address" in node_cfg and "pub_address" not in settings:
            settings["pub_address"] = node_cfg["pub_address"]
        if "id" in node_cfg and "node_id" not in settings:
            settings["node_id"] = str(node_cfg["id"])
        if "poll_ms" in display_cfg and "poll_ms" not in settings:
            settings["poll_ms"] = display_cfg["poll_ms"]

        if {"pub_address", "poll_ms"} <= settings.keys():
            break

    settings.setdefault("pub_address", "tcp://127.0.0.1:5555")
    settings.setdefault("poll_ms", 100)
    settings.setdefault("node_id", "animation")
    return settings


class PerfMonitor(QWidget):
    def __init__(self, sub_addr: str, poll_ms: int, node_id: str, logger):
        super().__init__()
        self.logger = logger
        self.poll_ms = poll_ms
        self._closed = False
        self.node_id = node_id
        self.node_topics = make_node_topics(node_id)

        self.setWindowTitle("Mochi Performance Monitor")
        # Escape closes the window (mirrors root.bind("<Escape>", ...)).
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)

        # --- ZMQ Subscriber ---
        self.ctx = zmq.Context.instance()
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.setsockopt(zmq.LINGER, 0)
        self.sub.setsockopt(zmq.RCVHWM, 1)
        self._sub_ready = False
        try:
            self.sub.connect(sub_addr)
            topic = self.node_topics.health
            self.sub.setsockopt(zmq.SUBSCRIBE, topic)
            logger.info(f"Health subscriber connected to {sub_addr} topic={topic.decode('utf-8')}")
            self._sub_ready = True
        except Exception as e:
            logger.error(f"Failed to connect ZMQ subscriber: {e}")
            self._closed = True
            # Defer the close until after construction/show so callers can
            # detect the failure via `winfo_exists`-style checks.
            QTimer.singleShot(0, self.close)
            return

        # --- UI Setup ---
        outer = QFrame(self)
        layout = QGridLayout(outer)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        root_layout = QGridLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(outer, 0, 0)

        name_font = QFont("Helvetica", 12)
        name_font.setBold(True)
        value_font = QFont("Menlo", 12)

        # The value labels, keyed by metric name. Replaces the tk.StringVars.
        self.metrics = {}
        initial_values = {
            "Node Size": "-- x --",
            "Mode": "--",
            "FPS": "--",
            "Frame Seq": "--",
            "Memory (MB)": "--",
            "Tx Rate (MB/s)": "--",
        }

        # Create a grid of labels
        for i, (name, value) in enumerate(initial_values.items()):
            label_name = QLabel(f"{name}:", outer)
            label_name.setFont(name_font)
            layout.addWidget(label_name, i, 0, Qt.AlignLeft)

            label_value = QLabel(value, outer)
            label_value.setFont(value_font)
            layout.addWidget(label_value, i, 1, Qt.AlignLeft)

            self.metrics[name] = label_value

        # Start polling for health messages (replaces root.after loop).
        self._timer = QTimer(self)
        self._timer.setInterval(self.poll_ms)
        self._timer.timeout.connect(self.poll_health)
        self._timer.start()

    def poll_health(self):
        if self._closed:
            return
        try:
            while True:
                topic, payload = self.sub.recv_multipart(flags=zmq.NOBLOCK)
                data = json.loads(payload.decode("utf-8"))
                self.update_metrics(data)
        except zmq.Again:
            pass  # No new message
        except Exception as e:
            self.logger.warning(f"Error receiving/parsing health data: {e}")

    def update_metrics(self, data):
        size_block = data.get("logical_size", {})
        width = size_block.get("width", data.get("w", "?"))
        height = size_block.get("height", data.get("h", "?"))
        mode = data.get("mode", "?")
        fps_target = data.get("fps_target", data.get("fps", 0))
        seq = data.get("sequence", data.get("seq", 0))
        memory_mb = data.get("memory_mb", data.get("mem_mb", 0.0))
        tx_rate = data.get("tx_rate_mbps", 0.0)

        self.metrics["Node Size"].setText(f"{width} x {height}")
        self.metrics["Mode"].setText(mode)
        self.metrics["FPS"].setText(f"{fps_target}")
        self.metrics["Frame Seq"].setText(f"{seq}")
        self.metrics["Memory (MB)"].setText(f"{memory_mb:.2f}")
        self.metrics["Tx Rate (MB/s)"].setText(f"{tx_rate:.3f}")

    def _on_close(self):
        self._closed = True
        try:
            self.sub.close(0)
        finally:
            super().close()

    def closeEvent(self, event):
        # Mirrors the tk WM_DELETE_WINDOW protocol handler: tear down the
        # subscriber socket exactly once before the window is destroyed.
        if not self._closed:
            self._closed = True
            try:
                if getattr(self, "sub", None) is not None and self._sub_ready:
                    self.sub.close(0)
            except Exception:
                pass
        super().closeEvent(event)


def main(argv=None) -> int:
    logger = logging.getLogger("MochiPerf")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    settings = _load_perf_settings(logger)
    pub_addr = str(settings.get("pub_address", "tcp://127.0.0.1:5555"))
    poll_ms = int(settings.get("poll_ms", 100))
    node_id = str(settings.get("node_id", "animation"))

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    win = PerfMonitor(sub_addr=pub_addr, poll_ms=poll_ms, node_id=node_id, logger=logger)
    if win._closed:
        return 1
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
