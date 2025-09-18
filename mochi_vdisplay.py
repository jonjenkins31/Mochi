# mochi_vdisplay.py — Virtual LED Display (Tkinter)
# Subscribes to ZeroMQ frames and renders a pixel grid.
# Matches mochi_node.py protocol: header ">HHQI" and topic b"frame".

import argparse
import struct
import time
import zmq
import tkinter as tk
from tkinter import ttk

# --- Protocol & transport (must match mochi_node.py) ---
HEADER_FMT = ">HHQI"   # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
SUB_ADDR_DEFAULT = "tcp://127.0.0.1:5555"

# --- Viewer defaults ---
PIXEL_SIZE_DEFAULT = 16   # LED cell size in screen pixels
MARGIN_DEFAULT = 8        # canvas margin
POLL_MS_DEFAULT = 5       # ZMQ polling cadence in ms


class VirtualDisplay:
    def __init__(self, root, sub_addr: str, pixel_size: int, margin: int, poll_ms: int):
        self.root = root
        self.pixel_size = int(max(2, pixel_size))
        self.margin = int(max(0, margin))
        self.poll_ms = int(max(1, poll_ms))

        root.title("Mochi Virtual Display — Tk")
        root.bind("q", lambda e: root.destroy())
        root.bind("<Escape>", lambda e: root.destroy())

        # Status bar
        self.status = tk.StringVar(value="Connecting…")
        self.fps_var = tk.StringVar(value="FPS: —")
        status_bar = ttk.Frame(root)
        ttk.Label(status_bar, textvariable=self.status).pack(side=tk.LEFT, padx=8)
        ttk.Label(status_bar, textvariable=self.fps_var).pack(side=tk.RIGHT, padx=8)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Canvas
        self.canvas = tk.Canvas(root, width=320, height=240, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # ZMQ subscriber
        self.ctx = zmq.Context.instance()
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.connect(sub_addr)
        # Python expects str for SUBSCRIBE in pyzmq when topic is text
        self.sub.setsockopt_string(zmq.SUBSCRIBE, FRAME_TOPIC.decode())
        self.status.set(f"SUB -> {sub_addr} topic='{FRAME_TOPIC.decode()}'  |  q/Esc to quit")

        # Grid state
        self.w = 0
        self.h = 0
        self.rects = []  # 2D list of rectangle IDs

        # FPS
        self._last_t = time.time()
        self._frames = 0

        # Start polling
        self.root.after(self.poll_ms, self.poll)

    def ensure_grid(self, w: int, h: int):
        if w == self.w and h == self.h and self.rects:
            return
        self.w, self.h = int(w), int(h)
        self.canvas.delete("all")
        self.rects = [[None for _ in range(self.w)] for _ in range(self.h)]
        width = self.margin*2 + self.w*self.pixel_size
        height = self.margin*2 + self.h*self.pixel_size
        self.canvas.config(width=width, height=height)
        for y in range(self.h):
            for x in range(self.w):
                x0 = self.margin + x*self.pixel_size
                y0 = self.margin + y*self.pixel_size
                x1 = x0 + self.pixel_size - 1
                y1 = y0 + self.pixel_size - 1
                rid = self.canvas.create_rectangle(x0, y0, x1, y1, outline="", fill="#000000")
                self.rects[y][x] = rid

    def poll(self):
        # Non-blocking receive; if no frame ready, reschedule
        try:
            topic, payload = self.sub.recv_multipart(flags=zmq.NOBLOCK)
        except zmq.Again:
            self.root.after(self.poll_ms, self.poll)
            return
        except Exception as e:
            self.status.set(f"ZMQ error: {e}")
            self.root.after(self.poll_ms, self.poll)
            return

        # Decode frame
        if len(payload) < HEADER_SIZE:
            self.status.set("Malformed payload: header too short")
            self.root.after(0, self.poll)
            return

        try:
            w, h, ts_ms, seq = struct.unpack_from(HEADER_FMT, payload, 0)
        except struct.error as e:
            self.status.set(f"Header unpack error: {e}")
            self.root.after(0, self.poll)
            return

        rgb = payload[HEADER_SIZE:]
        expected = w*h*3
        if len(rgb) != expected:
            self.status.set(f"Malformed frame: {len(rgb)}/{expected} bytes")
            self.root.after(0, self.poll)
            return

        # Resize grid if needed
        self.ensure_grid(w, h)

        # Update pixels
        mv = memoryview(rgb)
        idx = 0
        for y in range(h):
            row = self.rects[y]
            for x in range(w):
                r = mv[idx]; g = mv[idx+1]; b = mv[idx+2]
                idx += 3
                self.canvas.itemconfig(row[x], fill=f"#{r:02x}{g:02x}{b:02x}")

        # Update FPS roughly once per second
        self._frames += 1
        now = time.time()
        if now - self._last_t >= 1.0:
            fps = self._frames / (now - self._last_t)
            self.fps_var.set(f"FPS: {fps:.1f}")
            self._frames = 0
            self._last_t = now

        self.status.set(f"seq={seq}  {w}x{h}  ts={ts_ms}")

        # Schedule next poll immediately for smooth updates
        self.root.after(0, self.poll)


def parse_args():
    ap = argparse.ArgumentParser(description="Mochi Virtual Display (Tkinter)")
    ap.add_argument("--sub", default=SUB_ADDR_DEFAULT, help="SUB address for frames (default tcp://127.0.0.1:5555)")
    ap.add_argument("--pixel", type=int, default=PIXEL_SIZE_DEFAULT, help="LED pixel size in window pixels (default 16)")
    ap.add_argument("--margin", type=int, default=MARGIN_DEFAULT, help="Canvas margin (default 8)")
    ap.add_argument("--poll", type=int, default=POLL_MS_DEFAULT, help="Polling interval in ms (default 5)")
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
    VirtualDisplay(root, sub_addr=args.sub, pixel_size=args.pixel, margin=args.margin, poll_ms=args.poll)
    root.mainloop()


if __name__ == "__main__":
    main()