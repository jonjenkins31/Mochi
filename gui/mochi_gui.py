"""
Tk-based control panel for the Mochi animation node.

Provides manual controls for animations, scripts, and convenience launchers
for the virtual display and performance monitor.
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

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
import yaml
import zmq

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

from nodes.animation.plugin_core.logging_utils import setup_logger

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


class MochiGUI:
    def __init__(
        self,
        root,
        ctrl_addr: str,
        health_sub_addr: str,
        node_id: str,
        logger: logging.Logger,
        configured_plugins: list[dict] | None = None,
    ):
        self.root = root
        self.logger = logger
        root.title("Mochi Manual Control — Tk")
        self.ctrl_addr = ctrl_addr
        self.health_sub_addr = health_sub_addr
        self.node_id = node_id
        self.configured_plugins = configured_plugins or []
        self.node_topics = make_node_topics(node_id)
        self._processes: list[subprocess.Popen] = []

        # --- ZMQ command socket ---
        self.ctx = zmq.Context.instance()
        self.push = self.ctx.socket(zmq.PUSH)
        self.push.setsockopt(zmq.LINGER, 0)
        try:
            self.push.connect(self.ctrl_addr)
            self.logger.info(f"Command socket connected (PUSH) -> {self.ctrl_addr}")
        except zmq.error.ZMQError as exc:
            self.logger.error(f"Failed to connect to {self.ctrl_addr}: {exc}")
            messagebox.showerror(
                "ZMQ Error",
                f"Failed to connect to control address:\n{self.ctrl_addr}\nIs the node running?",
            )
            root.destroy()
            return
        time.sleep(0.05)  # allow the node to register our PUSH endpoint

        # --- UI ---
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        # Row 0: Node Status
        status_frame = ttk.LabelFrame(outer, text="Node Status")
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.status_metrics = {
            "Mode": tk.StringVar(value="--"),
            "Size": tk.StringVar(value="--"),
            "FPS": tk.StringVar(value="--"),
            "Mem (MB)": tk.StringVar(value="--"),
            "Tx (MB/s)": tk.StringVar(value="--"),
        }
        col = 0
        for name, var in self.status_metrics.items():
            ttk.Label(status_frame, text=f"{name}:").grid(row=0, column=col, sticky="w", padx=(10, 2))
            ttk.Label(status_frame, textvariable=var, font=("Menlo", 10)).grid(row=0, column=col + 1, sticky="w")
            col += 2
        status_frame.grid_columnconfigure(11, weight=1)

        # Row 1: Nodes overview and controls
        self.node_data: dict[str, dict] = {}
        self.selected_node: str | None = None

        nodes_frame = ttk.LabelFrame(outer, text="Nodes")
        nodes_frame.grid(row=1, column=0, sticky="nsew", pady=4)
        columns = ("node", "mode", "size", "fps", "mem", "tx")
        self.node_table = ttk.Treeview(nodes_frame, columns=columns, show="headings", height=4)
        headings = {
            "node": "Node",
            "mode": "Mode",
            "size": "Size",
            "fps": "FPS",
            "mem": "Mem (MB)",
            "tx": "Tx (MB/s)",
        }
        for col in columns:
            self.node_table.heading(col, text=headings[col])
            self.node_table.column(col, anchor=tk.W, stretch=True, width=90)
        self.node_table.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))
        self.node_table.bind("<<TreeviewSelect>>", self._on_node_select)

        node_ctrl = ttk.Frame(nodes_frame)
        node_ctrl.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Label(node_ctrl, text="Mode:").pack(side=tk.LEFT)
        self.node_mode_var = tk.StringVar(value="")
        node_entry = ttk.Entry(node_ctrl, textvariable=self.node_mode_var, width=24)
        node_entry.pack(side=tk.LEFT, padx=(4, 8))
        ttk.Button(node_ctrl, text="Turn On", command=self.command_mode_on).pack(side=tk.LEFT, padx=2)
        ttk.Button(node_ctrl, text="Turn Off", command=self.command_mode_off).pack(side=tk.LEFT, padx=2)
        ttk.Button(node_ctrl, text="Reset", command=self.command_mode_reset).pack(side=tk.LEFT, padx=2)

        self._populate_configured_nodes()

        # Row 2: MochiScript selection
        mscript_frame = ttk.LabelFrame(outer, text="MochiScript Control (.mscript)")
        mscript_frame.grid(row=2, column=0, sticky="ew", pady=4)

        self.mscript_var = tk.StringVar()
        try:
            mscript_list = sorted([p.name for p in MSCRIPTS_DIR.iterdir() if p.suffix == ".mscript"])
            self.mscript_combo = ttk.Combobox(
                mscript_frame, textvariable=self.mscript_var, values=mscript_list, state="readonly"
            )
            if mscript_list:
                self.mscript_var.set(mscript_list[0])
        except FileNotFoundError:
            self.logger.warning(f"MochiScripts directory not found: {MSCRIPTS_DIR}")
            self.mscript_combo = ttk.Combobox(
                mscript_frame, textvariable=self.mscript_var, values=["No mscripts found..."], state="disabled"
            )

        self.mscript_combo.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        ttk.Button(mscript_frame, text="Run", command=self.send_mscript_from_combobox).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(mscript_frame, text="Stop", command=self.stop_script).grid(row=0, column=2, padx=6, pady=6)
        mscript_frame.grid_columnconfigure(0, weight=1)

        # Row 3: Color picker
        color_row = ttk.LabelFrame(outer, text="Color Control")
        color_row.grid(row=3, column=0, sticky="ew", pady=4)
        self.color_preview = tk.Canvas(color_row, width=32, height=20, highlightthickness=1, highlightbackground="#888")
        self.color_preview.grid(row=0, column=0, padx=(8, 4), pady=6)
        ttk.Button(color_row, text="Pick Color…", command=self.pick_color).grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self.rgb_var = tk.StringVar(value="255 120 40")
        ttk.Entry(color_row, textvariable=self.rgb_var, width=12).grid(row=0, column=2, padx=6, pady=6, sticky="w")
        ttk.Button(color_row, text="Send", command=self.send_color_from_entry).grid(row=0, column=3, padx=6, pady=6)
        ttk.Label(color_row, text="Target:").grid(row=0, column=4, padx=(12, 4), pady=6, sticky="w")
        self.color_target_var = tk.StringVar(value="current")
        self.color_target_combo = ttk.Combobox(
            color_row,
            textvariable=self.color_target_var,
            values=("current", "solid_color"),
            state="readonly",
            width=12,
        )
        self.color_target_combo.grid(row=0, column=5, padx=6, pady=6, sticky="w")
        self.color_target_combo.current(0)
        color_row.grid_columnconfigure(6, weight=1)

        # Row 4: Matrix size
        size_row = ttk.LabelFrame(outer, text="Matrix Size (WxH)")
        size_row.grid(row=4, column=0, sticky="ew", pady=4)
        self.size_var = tk.StringVar(value="64x64")
        ttk.Entry(size_row, textvariable=self.size_var, width=10).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(size_row, text="Apply", command=self.send_size).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(size_row, text="Example: 64x32").grid(row=0, column=2, padx=6, pady=6)

        # Row 5: Raw command
        raw = ttk.LabelFrame(outer, text="Raw Command")
        raw.grid(row=5, column=0, sticky="ew", pady=4)
        self.cmd_var = tk.StringVar(value="")
        entry = ttk.Entry(raw, textvariable=self.cmd_var)
        entry.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        entry.bind("<Return>", lambda _e: self.send(self.cmd_var.get().strip()))
        ttk.Button(raw, text="Send", command=lambda: self.send(self.cmd_var.get().strip())).grid(
            row=0, column=1, padx=6, pady=6
        )
        raw.grid_columnconfigure(0, weight=1)

        # Row 6: Launchers
        launch_frame = ttk.LabelFrame(outer, text="Launch Tools")
        launch_frame.grid(row=6, column=0, sticky="ew", pady=4)
        ttk.Button(launch_frame, text="Launch Virtual Display", command=self.launch_vdisplay).pack(side=tk.LEFT, padx=6, pady=6)
        ttk.Button(launch_frame, text="Launch Performance Monitor", command=self.launch_perf_monitor).pack(side=tk.LEFT, padx=6, pady=6)
        ttk.Button(launch_frame, text="Launch Sprite Editor", command=self.launch_sprite_editor).pack(side=tk.LEFT, padx=6, pady=6)

        # Row 7: Footer
        footer = ttk.Frame(outer)
        footer.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        self.status = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Button(footer, text="Quit Node", command=lambda: self.send("quit")).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Close GUI", command=self.on_close).pack(side=tk.RIGHT, padx=6)

        root.bind("<Escape>", lambda _e: self.on_close())
        root.bind("q", lambda _e: self.on_close())

        self._set_preview_color(255, 120, 40)

        # Health subscriber
        self.health_queue: Queue = Queue()
        self.health_stop_event = threading.Event()
        self.health_thread = threading.Thread(target=self._health_poll_loop, daemon=True)
        self.health_thread.start()
        root.after(100, self._process_health_queue)

    def send_mscript_from_combobox(self) -> None:
        script_name = self.mscript_var.get()
        if script_name:
            script_path = MSCRIPTS_DIR / script_name
            if not script_path.exists():
                messagebox.showerror("Script Missing", f"Could not find script at: {script_path}")
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
            self.status.set(f"Sent: {msg}")
            self.logger.info(f"Sent command: {msg}")
        except Exception as exc:
            self.status.set(f"Error: {exc}")
            self.logger.error(f"Failed to send command: {exc}")

    def _send_node_command(self, command: str, *, require_selection: bool = False) -> bool:
        node_id = self._selected_node_id()
        if node_id is None:
            node_id = self.node_id
            if require_selection:
                messagebox.showwarning("No node", "Select a node to control.")
                return False
        msg = f"node {node_id} {command}"
        self.send(msg)
        return True

    def pick_color(self) -> None:
        rgb_tuple, _ = colorchooser.askcolor(title="Choose Bars Color")
        if not rgb_tuple:
            return
        r, g, b = (int(rgb_tuple[0]), int(rgb_tuple[1]), int(rgb_tuple[2]))
        self.rgb_var.set(f"{r} {g} {b}")
        self._set_preview_color(r, g, b)
        self._send_color_command(r, g, b)

    def send_color_from_entry(self) -> None:
        try:
            parts = [int(x) for x in self.rgb_var.get().split()]
            if len(parts) != 3:
                raise ValueError("Need 3 components")
            r, g, b = [max(0, min(255, p)) for p in parts]
        except Exception:
            messagebox.showerror("Invalid color", "Enter RGB as three integers: e.g. 255 120 40")
            return
        self._set_preview_color(r, g, b)
        self._send_color_command(r, g, b)

    def _selected_node_id(self) -> str | None:
        selection = self.node_table.selection()
        if not selection:
            return None
        return selection[0]

    def command_mode_on(self) -> None:
        mode = self.node_mode_var.get().strip()
        if not mode:
            messagebox.showwarning("No mode", "Enter a mode name to activate.")
            return
        self._send_node_command(f"mode on {mode}", require_selection=True)

    def command_mode_off(self) -> None:
        if not self._send_node_command("mode off", require_selection=True):
            return

    def command_mode_reset(self) -> None:
        mode = self.node_mode_var.get().strip()
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
        self.node_mode_var.set(mode)

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
                self.node_table.insert("", tk.END, iid=node_id, values=placeholder_values)
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
            self.node_table.selection_set(default_select)
            self.node_table.focus(default_select)
            self.selected_node = default_select
            self.node_mode_var.set(self.node_data.get(default_select, {}).get("mode", ""))

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

        if node_id in self.node_data:
            self.node_table.item(node_id, values=values)
        else:
            self.node_table.insert("", tk.END, iid=node_id, values=values)

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

        if not self.node_table.selection():
            self.node_table.selection_set(node_id)

        if node_id in self.node_table.selection():
            self.node_mode_var.set(mode)

    def _set_preview_color(self, r: int, g: int, b: int) -> None:
        self.color_preview.delete("all")
        self.color_preview.create_rectangle(0, 0, 32, 20, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

    def _send_color_command(self, r: int, g: int, b: int) -> None:
        target = (self.color_target_var.get() or "current").lower()
        if target != "current":
            command = f"color {target} {r} {g} {b}"
        else:
            command = f"color {r} {g} {b}"
        self._send_node_command(command)

    def send_size(self) -> None:
        s = self.size_var.get().lower().strip()
        if "x" not in s:
            messagebox.showerror("Invalid size", "Use format: WxH (e.g., 64x32)")
            return
        w, h = s.split("x", 1)
        try:
            w_i, h_i = int(w), int(h)
            if w_i <= 0 or h_i <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid size", "Width and height must be positive integers.")
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
            messagebox.showerror("Launch Error", f"Could not start {script.name}:\n{exc}")

    def launch_perf_monitor(self) -> None:
        script = GUI_DIR / "mochi_perf.py"
        self.logger.info(f"Launching {script.name}")
        try:
            p = subprocess.Popen([sys.executable, str(script)], cwd=str(GUI_DIR))
            self._processes.append(p)
        except Exception as exc:
            self.logger.error(f"Failed to launch perf monitor: {exc}")
            messagebox.showerror("Launch Error", f"Could not start {script.name}:\n{exc}")

    def launch_sprite_editor(self) -> None:
        script = TOOLS_DIR / "sprite_editor_gui.py"
        self.logger.info(f"Launching {script.name}")
        if not script.exists():
            msg = f"Sprite editor not found at {script}"
            self.logger.error(msg)
            messagebox.showerror("Launch Error", msg)
            return
        try:
            p = subprocess.Popen([sys.executable, str(script)], cwd=str(TOOLS_DIR))
            self._processes.append(p)
        except Exception as exc:
            self.logger.error(f"Failed to launch sprite editor: {exc}")
            messagebox.showerror("Launch Error", f"Could not start {script.name}:\n{exc}")

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
                    self.status.set(f"Health error: {data['error']}")
                    continue
                mode = data.get("mode") or data.get("data", {}).get("mode")
                size_block = data.get("logical_size", {})
                width = size_block.get("width", data.get("w", "?"))
                height = size_block.get("height", data.get("h", "?"))
                fps_target = data.get("fps_target", data.get("fps", 0))
                memory_mb = data.get("memory_mb", data.get("mem_mb", 0.0))
                tx_rate = data.get("tx_rate_mbps", 0.0)

                self.status_metrics["Mode"].set(mode or "?")
                self.status_metrics["Size"].set(f"{width}x{height}")
                self.status_metrics["FPS"].set(f"{fps_target}")
                self.status_metrics["Mem (MB)"].set(f"{memory_mb:.2f}")
                self.status_metrics["Tx (MB/s)"].set(f"{tx_rate:.3f}")

                self._update_node_row(data)
        except Empty:
            pass
        finally:
            if self.root.winfo_exists():
                self.root.after(100, self._process_health_queue)

    def on_close(self) -> None:
        self.health_stop_event.set()
        for proc in self._processes:
            if proc.poll() is None:
                proc.terminate()
        try:
            self.push.close(0)
        finally:
            self.root.destroy()


def main():
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

    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
    except Exception:
        pass

    app = MochiGUI(
        root,
        ctrl_addr=ctrl_addr,
        health_sub_addr=health_sub_addr,
        node_id=node_id,
        logger=logger,
        configured_plugins=plugin_entries,
    )
    if not root.winfo_exists():
        return

    root.mainloop()


if __name__ == "__main__":
    main()
