# mochi_gui.py — Manual control panel for Mochi (Tk + ZeroMQ PUB)
# Sends control commands to mochi_node.py on topic "ctrl".
#
# Commands supported by mochi_node.py:
#   mode <name>        (e.g., mode face | mode face_2 | mode bars | mode rainbow)
#   color R G B
#   size WxH
#   quit

import argparse
import time
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox

import zmq

CTRL_TOPIC = b"ctrl"
PUB_ADDR_DEFAULT = "tcp://127.0.0.1:5556"  # controller binds; node connects as SUB


class MochiGUI:
    def __init__(self, root, pub_addr: str):
        self.root = root
        self.root.title("Mochi Manual Control — Tk")
        self.pub_addr = pub_addr

        # --- ZMQ publisher ---
        self.ctx = zmq.Context.instance()
        self.pub = self.ctx.socket(zmq.PUB)
        self.pub.setsockopt(zmq.LINGER, 0)
        self.pub.bind(self.pub_addr)
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

        # Row 1: animation presets
        presets = ttk.LabelFrame(outer, text="Animations")
        presets.grid(row=1, column=0, sticky="ew", pady=4)
        buttons = [
            ("Face",    "mode face"),
            ("Face 2",  "mode face_2"),
            ("Bars",    "mode bars"),
            ("Rainbow", "mode rainbow"),
        ]
        for i, (label, cmd) in enumerate(buttons):
            ttk.Button(presets, text=label, command=lambda c=cmd: self.send(c)).grid(
                row=0, column=i, padx=6, pady=6, sticky="ew"
            )
            presets.grid_columnconfigure(i, weight=1)

        # Row 2: color for Bars
        color_row = ttk.LabelFrame(outer, text="Bars Color")
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
        self.size_var = tk.StringVar(value="32x32")
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

        # Row 5: footer
        footer = ttk.Frame(outer)
        footer.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.status = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status).pack(side=tk.LEFT)
        ttk.Button(footer, text="Quit Node", command=lambda: self.send("quit")).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Close GUI", command=self.on_close).pack(side=tk.RIGHT, padx=6)

        # Keyboard shortcuts (only close)
        root.bind("<Escape>", lambda e: self.on_close())
        root.bind("q", lambda e: self.on_close())

        # Initialize color preview
        self._set_preview_color(255, 120, 40)

    # ---- helpers ----
    def send(self, msg: str):
        msg = msg.strip()
        if not msg:
            return
        try:
            self.pub.send_multipart([CTRL_TOPIC, msg.encode()])
            self.status.set(f"Sent: {msg}")
        except Exception as e:
            self.status.set(f"Error: {e}")

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


def parse_args():
    ap = argparse.ArgumentParser(description="Mochi Manual Control GUI (Tk + ZeroMQ PUB)")
    ap.add_argument("--pub", default=PUB_ADDR_DEFAULT, help="PUB address for control (default tcp://127.0.0.1:5556)")
    return ap.parse_args()


def main():
    args = parse_args()
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
    except Exception:
        pass
    MochiGUI(root, pub_addr=args.pub)
    root.mainloop()


if __name__ == "__main__":
    main()