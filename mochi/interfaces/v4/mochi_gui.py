"""
Qt-based control panel for the Mochi animation node.

Provides manual controls for animations, scripts, and convenience launchers
for the virtual display and performance monitor.

This is a faithful PySide6 port of the original tkinter control panel. Only the
UI/widget/event-loop layer was rewritten; the zmq command sending, frame/health
decoding, threading and polling behavior are preserved 1:1.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

import yaml
import zmq

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
MSCRIPTS_DIR = PROJECT_ROOT / "assets" / "mscripts"
ROOT_CONFIG = PROJECT_ROOT / "config.yaml"
CONFIG_PATHS = [
    ROOT_CONFIG,
    PROJECT_ROOT / "plugins" / "animation_node" / "config.yaml",
]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from transport import make_node_topics

from mochi.nodes.animation.plugin_core.logging_utils import setup_logger

DEFAULT_CTRL_ADDR = "tcp://127.0.0.1:5556"
DEFAULT_HEALTH_ADDR = "tcp://127.0.0.1:5555"


def _load_configs(logger: logging.Logger):
    configs = []
    root_config: dict | None = None
    for path in CONFIG_PATHS:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            configs.append((path, data))
            if path == ROOT_CONFIG:
                root_config = data
        except FileNotFoundError:
            continue
        except yaml.YAMLError as exc:
            logger.warning(f"Cannot parse {path}: {exc}")
        except Exception as exc:
            logger.warning(f"Cannot read {path}: {exc}")
    return configs, (root_config or {})


def _lookup(configs, keys, default=None):
    for _, cfg in configs:
        value = cfg
        for key in keys:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if value is not None:
            return value
    return default


class MochiGUI(QMainWindow):
    def __init__(
        self,
        ctrl_addr: str,
        health_sub_addr: str,
        node_id: str,
        logger: logging.Logger,
        configured_plugins: list[dict] | None = None,
    ):
        super().__init__()
        self.logger = logger
        self.setWindowTitle("Mochi Manual Control — Qt")
        self.ctrl_addr = ctrl_addr
        self.health_sub_addr = health_sub_addr
        self.node_id = node_id
        self.configured_plugins = configured_plugins or []
        self.node_topics = make_node_topics(node_id)
        self._processes: list[subprocess.Popen] = []
        self._closed = False

        # --- ZMQ command socket ---
        self.ctx = zmq.Context.instance()
        self.push = self.ctx.socket(zmq.PUSH)
        self.push.setsockopt(zmq.LINGER, 0)
        try:
            self.push.connect(self.ctrl_addr)
            self.logger.info(f"Command socket connected (PUSH) -> {self.ctrl_addr}")
        except zmq.error.ZMQError as exc:
            self.logger.error(f"Failed to connect to {self.ctrl_addr}: {exc}")
            QMessageBox.critical(
                self,
                "ZMQ Error",
                f"Failed to connect to control address:\n{self.ctrl_addr}\nIs the node running?",
            )
            self._closed = True
            QTimer.singleShot(0, self.close)
            return
        time.sleep(0.05)  # allow the node to register our PUSH endpoint

        # --- UI ---
        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(4)

        # Row 0: Node Status
        status_frame = QGroupBox("Node Status")
        status_layout = QGridLayout(status_frame)
        self.status_metrics: dict[str, QLabel] = {}
        metric_names = ["Mode", "Size", "FPS", "Mem (MB)", "Tx (MB/s)"]
        col = 0
        for name in metric_names:
            status_layout.addWidget(QLabel(f"{name}:"), 0, col, Qt.AlignLeft)
            value_label = QLabel("--")
            value_label.setStyleSheet("font-family: Menlo; font-size: 10pt;")
            status_layout.addWidget(value_label, 0, col + 1, Qt.AlignLeft)
            self.status_metrics[name] = value_label
            col += 2
        status_layout.setColumnStretch(11, 1)
        outer.addWidget(status_frame)

        # Row 1: Nodes overview and controls
        self.node_data: dict[str, dict] = {}
        self.selected_node: str | None = None

        nodes_frame = QGroupBox("Nodes")
        nodes_layout = QVBoxLayout(nodes_frame)
        self._columns = ("node", "mode", "size", "fps", "mem", "tx")
        headings = {
            "node": "Node",
            "mode": "Mode",
            "size": "Size",
            "fps": "FPS",
            "mem": "Mem (MB)",
            "tx": "Tx (MB/s)",
        }
        self.node_table = QTreeWidget()
        self.node_table.setColumnCount(len(self._columns))
        self.node_table.setHeaderLabels([headings[c] for c in self._columns])
        self.node_table.setRootIsDecorated(False)
        self.node_table.setSelectionBehavior(QTreeWidget.SelectRows)
        self.node_table.setSelectionMode(QTreeWidget.SingleSelection)
        header = self.node_table.header()
        for i in range(len(self._columns)):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
        self._node_items: dict[str, QTreeWidgetItem] = {}
        self.node_table.itemSelectionChanged.connect(self._on_node_select)
        nodes_layout.addWidget(self.node_table)

        node_ctrl = QWidget()
        node_ctrl_layout = QHBoxLayout(node_ctrl)
        node_ctrl_layout.setContentsMargins(0, 0, 0, 0)
        node_ctrl_layout.addWidget(QLabel("Mode:"))
        self.node_mode_entry = QLineEdit()
        self.node_mode_entry.setFixedWidth(180)
        node_ctrl_layout.addWidget(self.node_mode_entry)
        btn_on = QPushButton("Turn On")
        btn_on.clicked.connect(self.command_mode_on)
        node_ctrl_layout.addWidget(btn_on)
        btn_off = QPushButton("Turn Off")
        btn_off.clicked.connect(self.command_mode_off)
        node_ctrl_layout.addWidget(btn_off)
        btn_reset = QPushButton("Reset")
        btn_reset.clicked.connect(self.command_mode_reset)
        node_ctrl_layout.addWidget(btn_reset)
        node_ctrl_layout.addStretch(1)
        nodes_layout.addWidget(node_ctrl)
        outer.addWidget(nodes_frame)

        self._populate_configured_nodes()

        # Row 2: MochiScript selection
        mscript_frame = QGroupBox("MochiScript Control (.mscript)")
        mscript_layout = QGridLayout(mscript_frame)
        self.mscript_combo = QComboBox()
        try:
            mscript_list = sorted([p.name for p in MSCRIPTS_DIR.iterdir() if p.suffix == ".mscript"])
            self.mscript_combo.addItems(mscript_list)
            if mscript_list:
                self.mscript_combo.setCurrentIndex(0)
        except FileNotFoundError:
            self.logger.warning(f"MochiScripts directory not found: {MSCRIPTS_DIR}")
            self.mscript_combo.addItems(["No mscripts found..."])
            self.mscript_combo.setEnabled(False)
        mscript_layout.addWidget(self.mscript_combo, 0, 0)
        mscript_run = QPushButton("Run")
        mscript_run.clicked.connect(self.send_mscript_from_combobox)
        mscript_layout.addWidget(mscript_run, 0, 1)
        mscript_stop = QPushButton("Stop")
        mscript_stop.clicked.connect(self.stop_script)
        mscript_layout.addWidget(mscript_stop, 0, 2)
        mscript_layout.setColumnStretch(0, 1)
        outer.addWidget(mscript_frame)

        # Row 3: Color picker
        color_row = QGroupBox("Color Control")
        color_layout = QGridLayout(color_row)
        self.color_preview = QFrame()
        self.color_preview.setFixedSize(32, 20)
        self.color_preview.setFrameShape(QFrame.Box)
        self.color_preview.setLineWidth(1)
        color_layout.addWidget(self.color_preview, 0, 0)
        pick_btn = QPushButton("Pick Color…")
        pick_btn.clicked.connect(self.pick_color)
        color_layout.addWidget(pick_btn, 0, 1, Qt.AlignLeft)
        self.rgb_entry = QLineEdit("255 120 40")
        self.rgb_entry.setFixedWidth(90)
        color_layout.addWidget(self.rgb_entry, 0, 2, Qt.AlignLeft)
        color_send = QPushButton("Send")
        color_send.clicked.connect(self.send_color_from_entry)
        color_layout.addWidget(color_send, 0, 3)
        color_layout.addWidget(QLabel("Target:"), 0, 4, Qt.AlignLeft)
        self.color_target_combo = QComboBox()
        self.color_target_combo.addItems(["current", "solid_color"])
        self.color_target_combo.setCurrentIndex(0)
        self.color_target_combo.setFixedWidth(100)
        color_layout.addWidget(self.color_target_combo, 0, 5, Qt.AlignLeft)
        color_layout.setColumnStretch(6, 1)
        outer.addWidget(color_row)

        # Row 4: Matrix size
        size_row = QGroupBox("Matrix Size (WxH)")
        size_layout = QGridLayout(size_row)
        self.size_entry = QLineEdit("64x64")
        self.size_entry.setFixedWidth(80)
        size_layout.addWidget(self.size_entry, 0, 0)
        size_apply = QPushButton("Apply")
        size_apply.clicked.connect(self.send_size)
        size_layout.addWidget(size_apply, 0, 1)
        size_layout.addWidget(QLabel("Example: 64x32"), 0, 2)
        size_layout.setColumnStretch(3, 1)
        outer.addWidget(size_row)

        # Row 5: Raw command
        raw = QGroupBox("Raw Command")
        raw_layout = QGridLayout(raw)
        self.cmd_entry = QLineEdit("")
        self.cmd_entry.returnPressed.connect(lambda: self.send(self.cmd_entry.text().strip()))
        raw_layout.addWidget(self.cmd_entry, 0, 0)
        raw_send = QPushButton("Send")
        raw_send.clicked.connect(lambda: self.send(self.cmd_entry.text().strip()))
        raw_layout.addWidget(raw_send, 0, 1)
        raw_layout.setColumnStretch(0, 1)
        outer.addWidget(raw)

        # Row 6: Launchers
        launch_frame = QGroupBox("Launch Tools")
        launch_layout = QHBoxLayout(launch_frame)
        vdisplay_btn = QPushButton("Launch Virtual Display")
        vdisplay_btn.clicked.connect(self.launch_vdisplay)
        launch_layout.addWidget(vdisplay_btn)
        perf_btn = QPushButton("Launch Performance Monitor")
        perf_btn.clicked.connect(self.launch_perf_monitor)
        launch_layout.addWidget(perf_btn)
        sprite_btn = QPushButton("Launch Sprite Editor")
        sprite_btn.clicked.connect(self.launch_sprite_editor)
        launch_layout.addWidget(sprite_btn)
        launch_layout.addStretch(1)
        outer.addWidget(launch_frame)

        # Row 7: Footer
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        self.status_label = QLabel("Ready")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch(1)
        close_btn = QPushButton("Close GUI")
        close_btn.clicked.connect(self.on_close)
        footer_layout.addWidget(close_btn)
        quit_btn = QPushButton("Quit Node")
        quit_btn.clicked.connect(lambda: self.send("quit"))
        footer_layout.addWidget(quit_btn)
        outer.addWidget(footer)

        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.on_close)
        QShortcut(QKeySequence(Qt.Key_Q), self, activated=self.on_close)

        self._set_preview_color(255, 120, 40)

        # Health subscriber
        self.health_queue: Queue = Queue()
        self.health_stop_event = threading.Event()
        self.health_thread = threading.Thread(target=self._health_poll_loop, daemon=True)
        self.health_thread.start()
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(100)
        self._health_timer.timeout.connect(self._process_health_queue)
        self._health_timer.start()

    # --- StringVar replacements (read/write widgets directly) ---

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    # --- Commands / logic (unchanged behavior) ---

    def send_mscript_from_combobox(self) -> None:
        script_name = self.mscript_combo.currentText()
        if script_name:
            script_path = MSCRIPTS_DIR / script_name
            if not script_path.exists():
                QMessageBox.critical(self, "Script Missing", f"Could not find script at: {script_path}")
                return
            relative = script_path.relative_to(PROJECT_ROOT).as_posix()
            self.send(f"play {relative}")

    def stop_script(self) -> None:
        self.send("stop")

    def send(self, msg: str) -> None:
        msg = msg.strip()
        if not msg:
            return
        try:
            self.push.send_string(msg)
            self._set_status(f"Sent: {msg}")
            self.logger.info(f"Sent command: {msg}")
        except Exception as exc:
            self._set_status(f"Error: {exc}")
            self.logger.error(f"Failed to send command: {exc}")

    def _send_node_command(self, command: str, *, require_selection: bool = False) -> bool:
        node_id = self._selected_node_id()
        if node_id is None:
            node_id = self.node_id
            if require_selection:
                QMessageBox.warning(self, "No node", "Select a node to control.")
                return False
        msg = f"node {node_id} {command}"
        self.send(msg)
        return True

    def pick_color(self) -> None:
        color = QColorDialog.getColor(parent=self, title="Choose Bars Color")
        if not color.isValid():
            return
        r, g, b = (int(color.red()), int(color.green()), int(color.blue()))
        self.rgb_entry.setText(f"{r} {g} {b}")
        self._set_preview_color(r, g, b)
        self._send_color_command(r, g, b)

    def send_color_from_entry(self) -> None:
        try:
            parts = [int(x) for x in self.rgb_entry.text().split()]
            if len(parts) != 3:
                raise ValueError("Need 3 components")
            r, g, b = [max(0, min(255, p)) for p in parts]
        except Exception:
            QMessageBox.critical(self, "Invalid color", "Enter RGB as three integers: e.g. 255 120 40")
            return
        self._set_preview_color(r, g, b)
        self._send_color_command(r, g, b)

    def _selected_node_id(self) -> str | None:
        items = self.node_table.selectedItems()
        if not items:
            return None
        return items[0].text(0)

    def command_mode_on(self) -> None:
        mode = self.node_mode_entry.text().strip()
        if not mode:
            QMessageBox.warning(self, "No mode", "Enter a mode name to activate.")
            return
        self._send_node_command(f"mode on {mode}", require_selection=True)

    def command_mode_off(self) -> None:
        if not self._send_node_command("mode off", require_selection=True):
            return

    def command_mode_reset(self) -> None:
        mode = self.node_mode_entry.text().strip()
        if mode:
            self._send_node_command(f"mode reset {mode}", require_selection=True)
        else:
            self._send_node_command("mode reset", require_selection=True)

    def _on_node_select(self, _event=None) -> None:
        node_id = self._selected_node_id()
        if not node_id:
            return
        self.selected_node = node_id
        data = self.node_data.get(node_id, {})
        mode = data.get("mode") or ""
        self.node_mode_entry.setText(mode)

    def _populate_configured_nodes(self) -> None:
        default_select: str | None = None
        for plugin in self.configured_plugins:
            node_id = str(plugin.get("id") or "").strip()
            if not node_id:
                continue
            plugin_type = (plugin.get("type") or "").lower()
            module_field = str(plugin.get("module") or "")
            if plugin_type and "node" not in plugin_type and not module_field.endswith(".node"):
                continue
            enabled = bool(plugin.get("enabled", True))
            status = "disabled" if not enabled else "offline"
            placeholder_values = (
                node_id,
                status,
                "-",
                "-" if enabled else "0",
                "-",
                "-",
            )
            if node_id not in self.node_data:
                item = QTreeWidgetItem([str(v) for v in placeholder_values])
                self.node_table.addTopLevelItem(item)
                self._node_items[node_id] = item
            self.node_data.setdefault(node_id, {})
            self.node_data[node_id].update({
                "mode": status,
                "size": "-",
                "fps": 0,
                "mem": 0.0,
                "tx": 0.0,
                "enabled": enabled,
                "online": False,
            })
            if default_select is None and enabled:
                default_select = node_id

        if default_select:
            item = self._node_items.get(default_select)
            if item is not None:
                self.node_table.setCurrentItem(item)
                item.setSelected(True)
            self.selected_node = default_select
            self.node_mode_entry.setText(self.node_data.get(default_select, {}).get("mode", ""))

    def _update_node_row(self, data: dict) -> None:
        node_id = str(data.get("node_id", self.node_id))
        size_block = data.get("logical_size", {})
        width = size_block.get("width", data.get("w", "?"))
        height = size_block.get("height", data.get("h", "?"))
        mode = data.get("mode") or data.get("data", {}).get("mode") or ""
        fps_target = data.get("fps_target", data.get("fps", 0))
        memory_mb = float(data.get("memory_mb", data.get("mem_mb", 0.0)) or 0.0)
        tx_rate = float(data.get("tx_rate_mbps", 0.0) or 0.0)

        values = (
            node_id,
            mode,
            f"{width}x{height}",
            f"{fps_target}",
            f"{memory_mb:.2f}",
            f"{tx_rate:.3f}",
        )

        item = self._node_items.get(node_id)
        if item is not None:
            for i, v in enumerate(values):
                item.setText(i, str(v))
        else:
            item = QTreeWidgetItem([str(v) for v in values])
            self.node_table.addTopLevelItem(item)
            self._node_items[node_id] = item

        entry = self.node_data.get(node_id, {}).copy()
        entry.update({
            "mode": mode,
            "size": f"{width}x{height}",
            "fps": fps_target,
            "memory_mb": memory_mb,
            "tx": tx_rate,
            "online": True,
        })
        self.node_data[node_id] = entry

        if not self.node_table.selectedItems():
            self.node_table.setCurrentItem(item)
            item.setSelected(True)

        if item in self.node_table.selectedItems():
            self.node_mode_entry.setText(mode)

    def _set_preview_color(self, r: int, g: int, b: int) -> None:
        color = QColor(r, g, b)
        self.color_preview.setStyleSheet(
            f"background-color: {color.name()}; border: 1px solid #888;"
        )

    def _send_color_command(self, r: int, g: int, b: int) -> None:
        target = (self.color_target_combo.currentText() or "current").lower()
        if target != "current":
            command = f"color {target} {r} {g} {b}"
        else:
            command = f"color {r} {g} {b}"
        self._send_node_command(command)

    def send_size(self) -> None:
        s = self.size_entry.text().lower().strip()
        if "x" not in s:
            QMessageBox.critical(self, "Invalid size", "Use format: WxH (e.g., 64x32)")
            return
        w, h = s.split("x", 1)
        try:
            w_i, h_i = int(w), int(h)
            if w_i <= 0 or h_i <= 0:
                raise ValueError
        except Exception:
            QMessageBox.critical(self, "Invalid size", "Width and height must be positive integers.")
            return
        self._send_node_command(f"size {w_i}x{h_i}")

    def launch_vdisplay(self) -> None:
        script = GUI_DIR / "mochi_vdisplay.py"
        self.logger.info(f"Launching {script.name}")
        try:
            p = subprocess.Popen([sys.executable, str(script)], cwd=str(GUI_DIR))
            self._processes.append(p)
        except Exception as exc:
            self.logger.error(f"Failed to launch virtual display: {exc}")
            QMessageBox.critical(self, "Launch Error", f"Could not start {script.name}:\n{exc}")

    def launch_perf_monitor(self) -> None:
        script = GUI_DIR / "mochi_perf.py"
        self.logger.info(f"Launching {script.name}")
        try:
            p = subprocess.Popen([sys.executable, str(script)], cwd=str(GUI_DIR))
            self._processes.append(p)
        except Exception as exc:
            self.logger.error(f"Failed to launch perf monitor: {exc}")
            QMessageBox.critical(self, "Launch Error", f"Could not start {script.name}:\n{exc}")

    def launch_sprite_editor(self) -> None:
        script = TOOLS_DIR / "sprite_editor_gui.py"
        self.logger.info(f"Launching {script.name}")
        if not script.exists():
            msg = f"Sprite editor not found at {script}"
            self.logger.error(msg)
            QMessageBox.critical(self, "Launch Error", msg)
            return
        try:
            p = subprocess.Popen([sys.executable, str(script)], cwd=str(TOOLS_DIR))
            self._processes.append(p)
        except Exception as exc:
            self.logger.error(f"Failed to launch sprite editor: {exc}")
            QMessageBox.critical(self, "Launch Error", f"Could not start {script.name}:\n{exc}")

    def _health_poll_loop(self) -> None:
        sub = self.ctx.socket(zmq.SUB)
        sub.setsockopt(zmq.RCVHWM, 1)
        try:
            # Subscribe to ALL node health topics
            topic_prefix = b"node."
            sub.setsockopt(zmq.SUBSCRIBE, topic_prefix)
            sub.connect(self.health_sub_addr)
            self.logger.info(
                "Health subscriber connected -> %s topic_prefix=%s",
                self.health_sub_addr, topic_prefix.decode("utf-8")
            )
        except Exception as exc:
            self.logger.error(f"Failed to connect health subscriber: {exc}")
            self.health_queue.put({"error": str(exc)})
            return

        while not self.health_stop_event.is_set():
            try:
                _, payload = sub.recv_multipart(flags=zmq.NOBLOCK)
                data = json.loads(payload.decode("utf-8"))
                self.health_queue.put(data)
            except zmq.Again:
                time.sleep(0.1)
            except Exception as exc:
                if not self.health_stop_event.is_set():
                    self.logger.warning(f"Error in health poller: {exc}")
        sub.close(0)

    def _process_health_queue(self) -> None:
        try:
            while not self.health_queue.empty():
                data = self.health_queue.get_nowait()
                if "error" in data:
                    self._set_status(f"Health error: {data['error']}")
                    continue
                mode = data.get("mode") or data.get("data", {}).get("mode")
                size_block = data.get("logical_size", {})
                width = size_block.get("width", data.get("w", "?"))
                height = size_block.get("height", data.get("h", "?"))
                fps_target = data.get("fps_target", data.get("fps", 0))
                memory_mb = data.get("memory_mb", data.get("mem_mb", 0.0))
                tx_rate = data.get("tx_rate_mbps", 0.0)

                self.status_metrics["Mode"].setText(mode or "?")
                self.status_metrics["Size"].setText(f"{width}x{height}")
                self.status_metrics["FPS"].setText(f"{fps_target}")
                self.status_metrics["Mem (MB)"].setText(f"{memory_mb:.2f}")
                self.status_metrics["Tx (MB/s)"].setText(f"{tx_rate:.3f}")

                self._update_node_row(data)
        except Empty:
            pass

    def on_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.health_stop_event.set()
        if hasattr(self, "_health_timer"):
            self._health_timer.stop()
        for proc in self._processes:
            if proc.poll() is None:
                proc.terminate()
        try:
            self.push.close(0)
        finally:
            self.close()

    def closeEvent(self, event) -> None:
        # Ensure teardown runs if the window is closed via the window manager.
        if not self._closed:
            self.on_close()
        super().closeEvent(event)


def main(argv=None) -> int:
    logger = setup_logger("MochiGUI")

    configs, root_config = _load_configs(logger)
    plugin_entries = list(root_config.get("plugins", []) or [])

    ctrl_addr = _lookup(configs, ("infrastructure", "gui", "ctrl_address"), None)
    if ctrl_addr is None:
        ctrl_addr = _lookup(configs, ("gui", "ctrl_address"), None)
    if ctrl_addr is None:
        ctrl_addr = _lookup(configs, ("gui", "pub_address"), None)
    if ctrl_addr is None:
        ctrl_addr = _lookup(configs, ("node", "ctrl_address"), DEFAULT_CTRL_ADDR)
    ctrl_addr = str(ctrl_addr or DEFAULT_CTRL_ADDR)

    health_sub_addr = _lookup(
        configs,
        ("infrastructure", "display", "sub_address"),
        _lookup(configs, ("node", "pub_address"), DEFAULT_HEALTH_ADDR),
    )
    health_sub_addr = str(health_sub_addr or DEFAULT_HEALTH_ADDR)

    default_node_id = _lookup(configs, ("node", "id"), None)
    if not default_node_id and plugin_entries:
        for plugin in plugin_entries:
            plugin_type = (plugin.get("type") or "").lower()
            module_field = str(plugin.get("module") or "")
            if "node" in plugin_type or module_field.endswith(".node"):
                default_node_id = plugin.get("id")
                if default_node_id:
                    break
    node_id = str(default_node_id or "animation")

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)

    window = MochiGUI(
        ctrl_addr=ctrl_addr,
        health_sub_addr=health_sub_addr,
        node_id=node_id,
        logger=logger,
        configured_plugins=plugin_entries,
    )
    if window._closed:
        return 0

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
