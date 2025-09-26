# mochi_gui.py — Manual control panel for Mochi (Tk + ZeroMQ PUB)
# Sends control commands to mochi_node.py on topic "ctrl".

import time
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import yaml
import zmq
import logging
import sys
import os
import subprocess
import threading
import json
from queue import Queue, Empty

# Add project root to path to allow importing core modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)
from core.logging_utils import setup_logger

# --- Constants ---
CTRL_TOPIC = b"ctrl"
HEALTH_TOPIC = b"health"
MSCRIPTS_DIR = os.path.join(PROJECT_ROOT, "mscripts")

class MochiGUI:
    def __init__(self, root, pub_addr: str, health_sub_addr: str, logger):
        self.root = root
        self.logger = logger
        self.root.title("Mochi Manual Control — Tk")
        self.pub_addr = pub_addr
        self.health_sub_addr = health_sub_addr
        self._processes = []

        # --- ZMQ publisher ---
        self.ctx = zmq.Context.instance()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.setsockopt(zmq.LINGER, 0)
        try:
            self.pub.bind(self.pub_addr)
            self.logger.info(f"Publisher bound to {self.pub_addr}")
        except zmq.error.ZMQError as e:
            self.logger.error(f"Failed to bind publisher to {self.pub_addr}: {e}")
            messagebox.showerror("ZMQ Error", f"Failed to bind to address: {self.pub_addr}\nIs another GUI instance running?")
            self.root.destroy()
            return
        time.sleep(0.1)  # slow-joiner allowance for node SUB to connect

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
        status_frame.grid_columnconfigure(11, weight=1) # Push to left

        # Row 1: MochiScript selection
        mscript_frame = ttk.LabelFrame(outer, text="MochiScript Control (.mscript)")
        mscript_frame.grid(row=1, column=0, sticky="ew", pady=4)

        self.mscript_var = tk.StringVar()
        try:
            mscript_list = sorted([f for f in os.listdir(MSCRIPTS_DIR) if f.endswith('.mscript')])
            self.mscript_combo = ttk.Combobox(mscript_frame, textvariable=self.mscript_var, values=mscript_list, state="readonly")
            if mscript_list:
                self.mscript_var.set(mscript_list[0])
        except FileNotFoundError:
            self.logger.warning(f"MochiScripts directory not found: {MSCRIPTS_DIR}")
            self.mscript_combo = ttk.Combobox(mscript_frame, textvariable=self.mscript_var, values=["No mscripts found..."], state="disabled")
        
        self.mscript_combo.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        ttk.Button(mscript_frame, text="Run", command=self.send_mscript_from_combobox).grid(row=0, column=1, padx=6, pady=6)
        ttk.Button(mscript_frame, text="Stop", command=self.stop_script).grid(row=0, column=2, padx=6, pady=6)
        mscript_frame.grid_columnconfigure(0, weight=1)

        # Row 2: color for Bars
        color_row = ttk.LabelFrame(outer, text="Color Control")
        color_row.grid(row=2, column=0, sticky="ew", pady=4)
        self.color_preview = tk.Canvas(color_row, width=32, height=20, highlightthickness=1, highlightbackground="#888")
        self.color_preview.grid(row=0, column=0, padx=(8, 4), pady=6)
        ttk.Button(color_row, text="Pick Color…", command=self.pick_color).grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self.rgb_var = tk.StringVar(value="255 120 40")
        ttk.Entry(color_row, textvariable=self.rgb_var, width=12).grid(row=0, column=2, padx=6, pady=6, sticky="w")
        ttk.Button(color_row, text="Send", command=self.send_color_from_entry).grid(row=0, column=3, padx=6, pady=6)

        # Row 3: size control
        size_row = ttk.LabelFrame(outer, text="Matrix Size (WxH)")
        size_row.grid(row=3, column=0, sticky="ew", pady=4)
        self.size_var = tk.StringVar(value="64x64") # Updated default
        ttk.Entry(size_row, textvariable=self.size_var, width=10).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(size_row, text="Apply", command=self.send_size).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(size_row, text="Example: 64x32").grid(row=0, column=2, padx=6, pady=6)

        # Row 4: raw command
        raw = ttk.LabelFrame(outer, text="Raw Command")
        raw.grid(row=4, column=0, sticky="ew", pady=4)
        self.cmd_var = tk.StringVar(value="")
        entry = ttk.Entry(raw, textvariable=self.cmd_var)
        entry.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        entry.bind("<Return>", lambda e: self.send(self.cmd_var.get().strip()))
        ttk.Button(raw, text="Send", command=lambda: self.send(self.cmd_var.get().strip())).grid(
            row=0, column=1, padx=6, pady=6
        )
        raw.grid_columnconfigure(0, weight=1)

        # Row 5: Launchers
        launch_frame = ttk.LabelFrame(outer, text="Launch Tools")
        launch_frame.grid(row=5, column=0, sticky="ew", pady=4)
        ttk.Button(launch_frame, text="Launch Virtual Display", command=self.launch_vdisplay).pack(side=tk.LEFT, padx=6, pady=6)
        ttk.Button(launch_frame, text="Launch Performance Monitor", command=self.launch_perf_monitor).pack(side=tk.LEFT, padx=6, pady=6)
        ttk.Button(launch_frame, text="Launch Sprite Editor", command=self.launch_sprite_editor).pack(side=tk.LEFT, padx=6, pady=6)

        # Row 6: footer
        footer = ttk.Frame(outer)
        footer.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        self.status = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Button(footer, text="Quit Node", command=lambda: self.send("quit")).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Close GUI", command=self.on_close).pack(side=tk.RIGHT, padx=6)

        # Keyboard shortcuts (only close)
        root.bind("<Escape>", lambda e: self.on_close())
        root.bind("q", lambda e: self.on_close())

        # Initialize color preview
        self._set_preview_color(255, 120, 40)

        # Health subscriber
        self.health_queue = Queue()
        self.health_stop_event = threading.Event()
        self.health_thread = threading.Thread(target=self._health_poll_loop, daemon=True)
        self.health_thread.start()
        self.root.after(100, self._process_health_queue)

    def send_mscript_from_combobox(self):
        script_name = self.mscript_var.get()
        if script_name:
            script_path = os.path.join(MSCRIPTS_DIR, script_name)
            self.send(f"play {script_path}")

    def stop_script(self):
        self.send("stop")

    def send(self, msg: str):
        msg = msg.strip()
        if not msg:
            return
        try:
            self.pub.send_multipart([CTRL_TOPIC, msg.encode()])
            self.status.set(f"Sent: {msg}")
            self.logger.info(f"Sent command: {msg}")
        except Exception as e:
            self.status.set(f"Error: {e}")
            self.logger.error(f"Failed to send command: {e}")

    def pick_color(self):
        rgb_tuple, _ = colorchooser.askcolor(title="Choose Bars Color")
        if not rgb_tuple:
            return
        r, g, b = (int(rgb_tuple[0]), int(rgb_tuple[1]), int(rgb_tuple[2]))
        self.rgb_var.set(f"{r} {g} {b}")
        self._set_preview_color(r, g, b)
        self.send(f"color {r} {g} {b}")

    def send_color_from_entry(self):
        try:
            parts = [int(x) for x in self.rgb_var.get().split()]
            if len(parts) != 3:
                raise ValueError("Need 3 components")
            r, g, b = [max(0, min(255, p)) for p in parts]
        except Exception:
            messagebox.showerror("Invalid color", "Enter RGB as three integers: e.g. 255 120 40")
            return
        self._set_preview_color(r, g, b)
        self.send(f"color {r} {g} {b}")

    def _set_preview_color(self, r, g, b):
        self.color_preview.delete("all")
        self.color_preview.create_rectangle(0, 0, 32, 20, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")

    def send_size(self):
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
        self.send(f"size {w_i}x{h_i}")

    def launch_vdisplay(self):
        self.logger.info("Launching mochi_vdisplay.py")
        try:
            p = subprocess.Popen([sys.executable, "mochi_vdisplay.py"])
            self._processes.append(p)
        except Exception as e:
            self.logger.error(f"Failed to launch vdisplay: {e}")
            messagebox.showerror("Launch Error", f"Could not start mochi_vdisplay.py:\n{e}")

    def launch_perf_monitor(self):
        self.logger.info("Launching mochi_perf.py")
        try:
            p = subprocess.Popen([sys.executable, "mochi_perf.py"])
            self._processes.append(p)
        except Exception as e:
            self.logger.error(f"Failed to launch perf monitor: {e}")
            messagebox.showerror("Launch Error", f"Could not start mochi_perf.py:\n{e}")

    def launch_sprite_editor(self):
        self.logger.info("Launching sprite_editor_gui.py")
        try:
            p = subprocess.Popen([sys.executable, "sprite_editor_gui.py"])
            self._processes.append(p)
        except Exception as e:
            self.logger.error(f"Failed to launch sprite editor: {e}")
            messagebox.showerror("Launch Error", f"Could not start sprite_editor_gui.py:\n{e}")

    def _health_poll_loop(self):
        sub = self.ctx.socket(zmq.SUB)
        sub.setsockopt(zmq.RCVHWM, 1)
        sub.connect(self.health_sub_addr)
        sub.setsockopt(zmq.SUBSCRIBE, HEALTH_TOPIC)
        self.logger.info(f"Health subscriber connected to {self.health_sub_addr}")

        while not self.health_stop_event.is_set():
            try:
                _, payload = sub.recv_multipart(flags=zmq.NOBLOCK)
                data = json.loads(payload.decode("utf-8"))
                self.health_queue.put(data)
            except zmq.Again:
                time.sleep(0.1)
            except Exception as e:
                self.logger.warning(f"Error in health poller: {e}")
        
        sub.close()

    def _process_health_queue(self):
        try:
            while not self.health_queue.empty():
                data = self.health_queue.get_nowait()
                self.status_metrics["Mode"].set(data.get('mode', '?'))
                self.status_metrics["Size"].set(f"{data.get('w','?')}x{data.get('h','?')}")
                self.status_metrics["FPS"].set(f"{data.get('fps', 0)}")
                self.status_metrics["Mem (MB)"].set(f"{data.get('mem_mb', 0):.2f}")
                self.status_metrics["Tx (MB/s)"].set(f"{data.get('tx_rate_mbps', 0):.3f}")
        except Empty:
            pass
        finally:
            if self.root.winfo_exists():
                self.root.after(100, self._process_health_queue)

    def on_close(self):
        self.health_stop_event.set()
        for p in self._processes:
            if p.poll() is None:
                p.terminate()
        try:
            self.pub.close(0)
        finally:
            self.root.destroy()

def main():
    # --- Logger Setup ---
    logger = setup_logger("MochiGUI")

    # --- Load Config ---
    try:
        config_path = os.path.join(PROJECT_ROOT, "config.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config.yaml not found. Please create it.")
        return
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config.yaml: {e}")
        return

    gui_config = config.get("gui", {})
    pub_addr = gui_config.get("pub_address", "tcp://127.0.0.1:5556")
    
    node_config = config.get("node", {})
    health_sub_addr = node_config.get("pub_address", "tcp://127.0.0.1:5555")

    # --- Run App ---
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
    except Exception:
        pass
    
    app = MochiGUI(root, pub_addr=pub_addr, health_sub_addr=health_sub_addr, logger=logger)
    if not root.winfo_exists(): # Check if window was destroyed due to error
        return
        
    root.mainloop()

if __name__ == "__main__":
    main()
