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
import animations  # Import the animations package

# --- Constants ---
CTRL_TOPIC = b"ctrl"
SCRIPTS_DIR = "scripts"

class MochiGUI:
    def __init__(self, root, pub_addr: str, logger):
        self.root = root
        self.logger = logger
        self.root.title("Mochi Manual Control — Tk")
        self.pub_addr = pub_addr

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

        # Row 0: connection info
        conn = ttk.Frame(outer)
        conn.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(conn, text="Publisher bound →").pack(side=tk.LEFT)
        self.addr_var = tk.StringVar(value=self.pub_addr)
        ttk.Label(conn, textvariable=self.addr_var, font=("Menlo", 10)).pack(side=tk.LEFT, padx=6)

        # Row 1: Dynamic animation selection
        anim_frame = ttk.LabelFrame(outer, text="Animation Control")
        anim_frame.grid(row=1, column=0, sticky="ew", pady=4)
        
        self.anim_var = tk.StringVar()
        try:
            anim_list = animations.list_names()
            self.anim_combo = ttk.Combobox(anim_frame, textvariable=self.anim_var, values=anim_list, state="readonly")
            if anim_list:
                self.anim_var.set(anim_list[0])
        except Exception as e:
            self.logger.error(f"Could not list animations: {e}")
            self.anim_combo = ttk.Combobox(anim_frame, textvariable=self.anim_var, values=["Error loading..."], state="disabled")
        
        self.anim_combo.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        ttk.Button(anim_frame, text="Play", command=self.send_mode_from_combobox).grid(row=0, column=1, padx=6, pady=6)
        anim_frame.grid_columnconfigure(0, weight=1)

        # Row 2: Script selection
        script_frame = ttk.LabelFrame(outer, text="Script Control")
        script_frame.grid(row=2, column=0, sticky="ew", pady=4)

        self.script_var = tk.StringVar()
        try:
            script_list = [f for f in os.listdir(SCRIPTS_DIR) if f.endswith('.json')]
            self.script_combo = ttk.Combobox(script_frame, textvariable=self.script_var, values=script_list, state="readonly")
            if script_list:
                self.script_var.set(script_list[0])
        except FileNotFoundError:
            self.logger.warning(f"Scripts directory not found: {SCRIPTS_DIR}")
            self.script_combo = ttk.Combobox(script_frame, textvariable=self.script_var, values=["No scripts found..."], state="disabled")
        
        self.script_combo.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        ttk.Button(script_frame, text="Run", command=self.send_script_from_combobox).grid(row=0, column=1, padx=6, pady=6)
        script_frame.grid_columnconfigure(0, weight=1)

        # Row 3: color for Bars
        color_row = ttk.LabelFrame(outer, text="Color Control")
        color_row.grid(row=3, column=0, sticky="ew", pady=4)
        self.color_preview = tk.Canvas(color_row, width=32, height=20, highlightthickness=1, highlightbackground="#888")
        self.color_preview.grid(row=0, column=0, padx=(8, 4), pady=6)
        ttk.Button(color_row, text="Pick Color…", command=self.pick_color).grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self.rgb_var = tk.StringVar(value="255 120 40")
        ttk.Entry(color_row, textvariable=self.rgb_var, width=12).grid(row=0, column=2, padx=6, pady=6, sticky="w")
        ttk.Button(color_row, text="Send", command=self.send_color_from_entry).grid(row=0, column=3, padx=6, pady=6)

        # Row 4: size control
        size_row = ttk.LabelFrame(outer, text="Matrix Size (WxH)")
        size_row.grid(row=4, column=0, sticky="ew", pady=4)
        self.size_var = tk.StringVar(value="64x64") # Updated default
        ttk.Entry(size_row, textvariable=self.size_var, width=10).grid(row=0, column=0, padx=6, pady=6)
        ttk.Button(size_row, text="Apply", command=self.send_size).grid(row=0, column=1, padx=6, pady=6)
        ttk.Label(size_row, text="Example: 64x32").grid(row=0, column=2, padx=6, pady=6)

        # Row 5: raw command
        raw = ttk.LabelFrame(outer, text="Raw Command")
        raw.grid(row=5, column=0, sticky="ew", pady=4)
        self.cmd_var = tk.StringVar(value="")
        entry = ttk.Entry(raw, textvariable=self.cmd_var)
        entry.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        entry.bind("<Return>", lambda e: self.send(self.cmd_var.get().strip()))
        ttk.Button(raw, text="Send", command=lambda: self.send(self.cmd_var.get().strip())).grid(
            row=0, column=1, padx=6, pady=6
        )
        raw.grid_columnconfigure(0, weight=1)

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

    def send_mode_from_combobox(self):
        anim_name = self.anim_var.get()
        if anim_name:
            self.send(f"mode {anim_name}")

    def send_script_from_combobox(self):
        script_name = self.script_var.get()
        if script_name:
            self.send(f"play {os.path.join(SCRIPTS_DIR, script_name)}")

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

    def on_close(self):
        try:
            self.pub.close(0)
        finally:
            self.root.destroy()

def main():
    # --- Logger Setup ---
    logger = logging.getLogger("MochiGUI")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Handler for stdout (INFO)
    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(lambda record: record.levelno == logging.INFO)
    info_handler.setFormatter(formatter)
    # Handler for stderr (WARNING, ERROR, CRITICAL)
    err_handler = logging.StreamHandler(sys.stderr)
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(formatter)
    logger.addHandler(info_handler)
    logger.addHandler(err_handler)

    # --- Load Config ---
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config.yaml not found. Please create it.")
        return
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config.yaml: {e}")
        return

    gui_config = config.get("gui", {})
    pub_addr = gui_config.get("pub_address", "tcp://127.0.0.1:5556")

    # --- Run App ---
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
    except Exception:
        pass
    
    app = MochiGUI(root, pub_addr=pub_addr, logger=logger)
    if not root.winfo_exists(): # Check if window was destroyed due to error
        return
        
    root.mainloop()

if __name__ == "__main__":
    main()
