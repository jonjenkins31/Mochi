# mochi_perf.py
# A simple performance and health monitor for a Mochi node.

import tkinter as tk
from tkinter import ttk
import zmq
import json
import logging
import sys
import yaml

# --- Constants ---
HEALTH_TOPIC = b"health"

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

    try:
        with open("../config.yaml", "r") as f: config = yaml.safe_load(f)
    except Exception as e: logger.error(f"Cannot load config.yaml: {e}"); return

    # The performance monitor connects to the node's PUB address
    node_config = config.get("node", {})
    pub_addr = node_config.get("pub_address", "tcp://127.0.0.1:5555")
    
    display_config = config.get("display", {})
    poll_ms = int(display_config.get("poll_ms", 100)) # Poll less frequently than vdisplay

    root = tk.Tk()
    app = PerfMonitor(root, sub_addr=pub_addr, poll_ms=poll_ms, logger=logger)
    if not root.winfo_exists(): return
    root.mainloop()

if __name__ == "__main__":
    main()
