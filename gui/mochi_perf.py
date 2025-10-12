# mochi_perf.py
# A simple performance and health monitor for a Mochi node.

import json
import logging
import sys
from pathlib import Path

import tkinter as tk
from tkinter import ttk
import yaml
import zmq

# --- Constants ---
HEALTH_TOPIC = b"health"

# The root directory of the Mochi project.
GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
CONFIG_PATHS = [
    PROJECT_ROOT / "config.yaml",
    PROJECT_ROOT / "plugins" / "animation_node" / "config.yaml",
]


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
        if "poll_ms" in display_cfg and "poll_ms" not in settings:
            settings["poll_ms"] = display_cfg["poll_ms"]

        if {"pub_address", "poll_ms"} <= settings.keys():
            break

    settings.setdefault("pub_address", "tcp://127.0.0.1:5555")
    settings.setdefault("poll_ms", 100)
    return settings

class PerfMonitor:
    def __init__(self, root, sub_addr: str, poll_ms: int, logger):
        self.root = root
        self.logger = logger
        self.poll_ms = poll_ms
        self._closed = False

        root.title("Mochi Performance Monitor")
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Escape>", lambda e: self._on_close())

        # --- ZMQ Subscriber ---
        self.ctx = zmq.Context.instance()
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.setsockopt(zmq.LINGER, 0)
        self.sub.setsockopt(zmq.RCVHWM, 1)
        try:
            self.sub.connect(sub_addr)
            self.sub.setsockopt(zmq.SUBSCRIBE, HEALTH_TOPIC)
            logger.info(f"Health subscriber connected to {sub_addr}")
        except Exception as e:
            logger.error(f"Failed to connect ZMQ subscriber: {e}")
            self.root.destroy()
            return

        # --- UI Setup ---
        outer = ttk.Frame(root, padding=15)
        outer.pack(fill=tk.BOTH, expand=True)

        self.metrics = {
            "Node Size": tk.StringVar(value="-- x --"),
            "Mode": tk.StringVar(value="--"),
            "FPS": tk.StringVar(value="--"),
            "Frame Seq": tk.StringVar(value="--"),
            "Memory (MB)": tk.StringVar(value="--"),
            "Tx Rate (MB/s)": tk.StringVar(value="--"),
        }

        # Create a grid of labels
        for i, (name, var) in enumerate(self.metrics.items()):
            label_name = ttk.Label(outer, text=f"{name}:", font=("Helvetica", 12, "bold"))
            label_name.grid(row=i, column=0, sticky="w", padx=5, pady=5)
            
            label_value = ttk.Label(outer, textvariable=var, font=("Menlo", 12))
            label_value.grid(row=i, column=1, sticky="w", padx=5, pady=5)

        # Start polling for health messages
        self.root.after(self.poll_ms, self.poll_health)

    def poll_health(self):
        if self._closed: return
        try:
            while True:
                topic, payload = self.sub.recv_multipart(flags=zmq.NOBLOCK)
                data = json.loads(payload.decode("utf-8"))
                self.update_metrics(data)
        except zmq.Again:
            pass # No new message
        except Exception as e:
            self.logger.warning(f"Error receiving/parsing health data: {e}")
        
        self.root.after(self.poll_ms, self.poll_health)

    def update_metrics(self, data):
        self.metrics["Node Size"].set(f"{data.get('w', '?')} x {data.get('h', '?')}")
        self.metrics["Mode"].set(data.get('mode', '?'))
        self.metrics["FPS"].set(f"{data.get('fps', 0)}")
        self.metrics["Frame Seq"].set(f"{data.get('seq', 0)}")
        self.metrics["Memory (MB)"].set(f"{data.get('mem_mb', 0):.2f}")
        self.metrics["Tx Rate (MB/s)"].set(f"{data.get('tx_rate_mbps', 0):.3f}")

    def _on_close(self):
        self._closed = True
        try:
            self.sub.close(0)
        finally:
            self.root.destroy()

def main():
    logger = logging.getLogger("MochiPerf")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    settings = _load_perf_settings(logger)
    pub_addr = str(settings.get("pub_address", "tcp://127.0.0.1:5555"))
    poll_ms = int(settings.get("poll_ms", 100))

    root = tk.Tk()
    app = PerfMonitor(root, sub_addr=pub_addr, poll_ms=poll_ms, logger=logger)
    if not root.winfo_exists(): return
    root.mainloop()

if __name__ == "__main__":
    main()
