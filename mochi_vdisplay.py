# mochi_vdisplay.py — Minimal Virtual LED Display (Tkinter)
# Subscribes to ZeroMQ frames and shows them as a single blitted image (no per-pixel rectangles).
# Protocol: topic b"frame", payload = header ">HHQI" + RGB bytes (w*h*3).

import os
import struct
import time
import zmq
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk  # requires pillow

# --- Protocol & transport (must match mochi_node.py) ---
HEADER_FMT = ">HHQI"   # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"
SUB_ADDR_DEFAULT = "tcp://127.0.0.1:5555"

# --- Viewer defaults ---
ZOOM_DEFAULT = 8          # nearest-neighbor zoom factor
POLL_MS_DEFAULT = 5       # ZMQ polling cadence in ms


class VirtualDisplay:
    def __init__(self, root, sub_addr: str = SUB_ADDR_DEFAULT, zoom: int = ZOOM_DEFAULT, poll_ms: int = POLL_MS_DEFAULT):
        self.root = root
        self.poll_ms = int(max(1, poll_ms))

        root.title("Mochi Virtual Display — Tk")
        root.bind("q", lambda e: root.destroy())
        root.bind("<Escape>", lambda e: root.destroy())
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.resizable(False, False)

        # UI state
        self.status = tk.StringVar(value="")
        self.fps_var = tk.StringVar(value="FPS: --")
        self._closed = False

        # Status bar
        self.status_bar = ttk.Frame(root)
        ttk.Label(self.status_bar, textvariable=self.status).pack(side=tk.LEFT, padx=8)
        ttk.Label(self.status_bar, textvariable=self.fps_var).pack(side=tk.RIGHT, padx=8)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Image label (single blit per frame) instead of thousands of rectangles
        self.img_label = ttk.Label(root)
        self.img_label.pack()  # no fill/expand; we will size the toplevel to match the image
        self.photo = None
        self.zoom = int(max(1, zoom))  # integer zoom factor
        self._disp_size = (0, 0)  # cached (w*zoom, h*zoom)

        # ZMQ subscriber
        self.ctx = zmq.Context.instance()
        self.sub = self.ctx.socket(zmq.SUB)
        # keep socket lean/real-time
        self.sub.setsockopt(zmq.LINGER, 0)
        self.sub.setsockopt(zmq.RCVHWM, 1)
        # NOTE: avoid CONFLATE on multipart SUB; we manually drain to latest
        self.sub.connect(sub_addr)
        # Subscribe to the binary topic (avoid implicit UTF-8 conversions)
        self.sub.setsockopt(zmq.SUBSCRIBE, FRAME_TOPIC)
        self.status.set(f"SUB -> {sub_addr} topic='{FRAME_TOPIC.decode()}'  |  q/Esc to quit")

        # Frame state
        self.w = 0
        self.h = 0

        # FPS
        self._last_t = time.time()
        self._frames = 0

        # Zero-copy from ZMQ can expose buggy libzmq builds on macOS; default to copies unless explicitly enabled.
        self._zero_copy = os.getenv("MOCHI_VDISPLAY_ZERO_COPY", "0") in ("1", "true", "TRUE")

        # Start polling
        self.root.after(self.poll_ms, self.poll)

    def _on_close(self):
        try:
            # Stop future polls
            self._closed = True
            # Close ZMQ pieces
            try:
                self.sub.close(0)
            except Exception:
                pass
            # Do not terminate the global Context.instance()
        finally:
            self.root.destroy()

    def ensure_grid(self, w: int, h: int):
        # record current source size (used for info/FPS only)
        self.w, self.h = int(w), int(h)

    def _lock_to_image(self, dw: int, dh: int):
        """Lock the window size to image size + status bar height; disallow user resize."""
        try:
            # Ask Tk to compute requested sizes for widgets
            self.root.update_idletasks()
            # Height of status bar
            sb_h = self.status_bar.winfo_reqheight() if self.status_bar.winfo_ismapped() else 0
            total_w = dw
            total_h = dh + sb_h
            # Apply exact geometry and lock it
            self.root.geometry(f"{total_w}x{total_h}")
            self.root.minsize(total_w, total_h)
            self.root.maxsize(total_w, total_h)
            self.root.resizable(False, False)
        except Exception:
            pass

    def poll(self):
        # Drain any queued frames so we render only the newest one (avoids backpressure without CONFLATE)
        got_any = False
        last_payload_mv = None
        try:
            while True:
                if self._zero_copy:
                    topic_frame, payload_frame = self.sub.recv_multipart(flags=zmq.NOBLOCK, copy=False)
                    last_payload_mv = memoryview(payload_frame.buffer)
                else:
                    topic_frame, payload_bytes = self.sub.recv_multipart(flags=zmq.NOBLOCK, copy=True)
                    last_payload_mv = memoryview(payload_bytes)
                got_any = True
        except zmq.Again:
            if not got_any:
                self.root.after(self.poll_ms, self.poll)
                return
        except Exception as e:
            self.status.set(f"ZMQ error: {e}")
            self.root.after(self.poll_ms, self.poll)
            return
        payload_mv = last_payload_mv

        if len(payload_mv) < HEADER_SIZE:
            self.status.set("Malformed payload: header too short")
            self.root.after(self.poll_ms, self.poll)
            return
        try:
            w, h, ts_ms, seq = struct.unpack_from(HEADER_FMT, payload_mv, 0)
        except struct.error as e:
            self.status.set(f"Header unpack error: {e}")
            self.root.after(self.poll_ms, self.poll)
            return
        rgb_mv = payload_mv[HEADER_SIZE:]
        expected = w * h * 3
        if w <= 0 or h <= 0 or expected <= 0 or expected > 10_000_000:
            self.status.set(f"Suspicious frame size {w}x{h}")
            self.root.after(self.poll_ms, self.poll)
            return
        if len(rgb_mv) != expected:
            self.status.set(f"Malformed frame: {len(rgb_mv)}/{expected} bytes")
            self.root.after(self.poll_ms, self.poll)
            return

        # record size and build image directly from buffer (zero-copy source)
        self.ensure_grid(w, h)
        im = Image.frombuffer("RGB", (w, h), rgb_mv, "raw", "RGB", 0, 1)
        dw, dh = w * self.zoom, h * self.zoom
        if self.zoom != 1:
            im = im.resize((dw, dh), resample=Image.NEAREST)

        # If the display size is unchanged, reuse the PhotoImage and paste
        if self.photo is not None and self._disp_size == (dw, dh):
            try:
                self.photo.paste(im)
            except Exception:
                # Fallback to recreating the image (rare)
                self.photo = ImageTk.PhotoImage(im)
                self.img_label.configure(image=self.photo)
                self._lock_to_image(dw, dh)
        else:
            self.photo = ImageTk.PhotoImage(im)
            self.img_label.configure(image=self.photo)
            self._disp_size = (dw, dh)
            self._lock_to_image(dw, dh)

        # Update FPS roughly once per second
        self._frames += 1
        now = time.time()
        if now - self._last_t >= 1.0:
            fps = self._frames / (now - self._last_t)
            self.fps_var.set(f"FPS: {fps:.1f}")
            self._frames = 0
            self._last_t = now

        self.status.set(f"seq={seq}  {w}x{h}  ts={ts_ms}  zero_copy={'on' if self._zero_copy else 'off'}")

        # Schedule promptly but via idle to let Tk flush
        if not self._closed:
            self.root.after_idle(self.poll)


def main():
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "aqua" in style.theme_names():
            style.theme_use("aqua")
    except Exception:
        pass
    # Minimal: default address and zoom; override via env if desired
    sub_addr = os.getenv("MOCHI_VDISPLAY_SUB", SUB_ADDR_DEFAULT)
    zoom = int(os.getenv("MOCHI_VDISPLAY_ZOOM", str(ZOOM_DEFAULT)))
    poll_ms = int(os.getenv("MOCHI_VDISPLAY_POLL", str(POLL_MS_DEFAULT)))
    VirtualDisplay(root, sub_addr=sub_addr, zoom=zoom, poll_ms=poll_ms)
    root.mainloop()


if __name__ == "__main__":
    main()