# mochi_vdisplay.py — Minimal Virtual LED Display (Tkinter)
# This client receives small, logical frames and performs a pixel-perfect upscale.

import struct
import time
from pathlib import Path

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import yaml
import logging
import sys
import zmq

# --- Protocol & transport (must match mochi_node.py) ---
HEADER_FMT = ">HHQI"   # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FRAME_TOPIC = b"frame"

# The root directory of the Mochi project.
GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
CONFIG_PATHS = [
    PROJECT_ROOT / "config.yaml",
    PROJECT_ROOT / "plugins" / "animation_node" / "config.yaml",
]


def _load_display_settings(logger):
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

        display_cfg = cfg.get("display") or {}
        node_cfg = cfg.get("node") or {}
        if display_cfg:
            settings.setdefault("sub_address", display_cfg.get("sub_address"))
            settings.setdefault("zoom", display_cfg.get("zoom"))
            settings.setdefault("poll_ms", display_cfg.get("poll_ms"))
        if "sub_address" not in settings:
            if "pub_address" in node_cfg:
                settings["sub_address"] = node_cfg["pub_address"]

        # If we already have everything we need, stop searching.
        if {"sub_address", "zoom", "poll_ms"} <= settings.keys():
            break

    settings.setdefault("sub_address", "tcp://127.0.0.1:5555")
    settings.setdefault("zoom", 8)
    settings.setdefault("poll_ms", 5)
    return settings

class VirtualDisplay:
    def __init__(self, root, sub_addr: str, zoom: int, poll_ms: int, logger):
        self.root = root
        self.logger = logger
        self.poll_ms = int(max(1, poll_ms))
        self.zoom = int(max(1, zoom))

        root.title("Mochi Virtual Display — Tk")
        root.bind("q", lambda e: root.destroy())
        root.bind("<Escape>", lambda e: root.destroy())
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.status = tk.StringVar(value="")
        self.fps_var = tk.StringVar(value="FPS: --")
        self._closed = False

        self.status_bar = ttk.Frame(root)
        ttk.Label(self.status_bar, textvariable=self.status).pack(side=tk.LEFT, padx=8)
        ttk.Label(self.status_bar, textvariable=self.fps_var).pack(side=tk.RIGHT, padx=8)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.img_label = ttk.Label(root)
        self.img_label.pack(fill=tk.BOTH, expand=True)
        self.photo = None
        self._disp_size = (0, 0)

        self.ctx = zmq.Context.instance()
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.setsockopt(zmq.LINGER, 0)
        self.sub.setsockopt(zmq.RCVHWM, 1)
        try:
            self.sub.connect(sub_addr)
            self.logger.info(f"Subscriber connected to {sub_addr}")
        except zmq.error.ZMQError as e:
            self.logger.error(f"Failed to connect subscriber to {sub_addr}: {e}")
            self.root.destroy()
            return
            
        self.sub.setsockopt(zmq.SUBSCRIBE, FRAME_TOPIC)
        self.status.set(f"SUB -> {sub_addr} topic='{FRAME_TOPIC.decode()}'  |  q/Esc to quit")

        self._last_t = time.time()
        self._frames = 0
        self.root.after(self.poll_ms, self.poll)

    def _on_close(self):
        self._closed = True
        try:
            self.sub.close(0)
        finally:
            self.root.destroy()

    def _lock_to_image(self, dw: int, dh: int):
        try:
            self.root.update_idletasks()
            sb_h = self.status_bar.winfo_reqheight() if self.status_bar.winfo_ismapped() else 0
            total_w, total_h = dw, dh + sb_h
            self.root.geometry(f"{total_w}x{total_h}")
            self.root.minsize(total_w, total_h)
            self.root.maxsize(total_w, total_h)
        except Exception as e:
            self.logger.warning(f"Failed to lock window size: {e}")

    def poll(self):
        if self._closed: return
        try:
            topic, payload = self.sub.recv_multipart(flags=zmq.NOBLOCK)
        except zmq.Again:
            self.root.after(self.poll_ms, self.poll)
            return
        except Exception as e:
            self.status.set(f"ZMQ error: {e}")
            self.root.after(self.poll_ms, self.poll)
            return
        
        if len(payload) < HEADER_SIZE: self.root.after(self.poll_ms, self.poll); return
        try:
            w, h, ts_ms, seq = struct.unpack_from(HEADER_FMT, payload, 0)
        except struct.error: self.root.after(self.poll_ms, self.poll); return
        
        rgb_mv = memoryview(payload)[HEADER_SIZE:]
        expected = w * h * 3
        if w <= 0 or h <= 0 or len(rgb_mv) != expected: self.root.after(self.poll_ms, self.poll); return

        im_logical = Image.frombuffer("RGB", (w, h), rgb_mv, "raw", "RGB", 0, 1)
        
        dw, dh = w * self.zoom, h * self.zoom
        if self.zoom > 1:
            im_display = im_logical.resize((dw, dh), resample=Image.NEAREST)
        else:
            im_display = im_logical

        if self.photo is not None and self._disp_size == (dw, dh):
            try: self.photo.paste(im_display)
            except Exception: self.photo = ImageTk.PhotoImage(im_display); self.img_label.configure(image=self.photo)
        else:
            self.photo = ImageTk.PhotoImage(im_display)
            self.img_label.configure(image=self.photo)
            self._disp_size = (dw, dh)
            self._lock_to_image(dw, dh)

        self._frames += 1
        now = time.time()
        if now - self._last_t >= 1.0:
            fps = self._frames / (now - self._last_t)
            self.fps_var.set(f"FPS: {fps:.1f}")
            self._frames = 0
            self._last_t = now

        self.status.set(f"seq={seq}  {w}x{h} -> {dw}x{dh}  ts={ts_ms}")

        self.root.after_idle(self.poll)

def main():
    logger = logging.getLogger("MochiVDisplay")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    info_handler = logging.StreamHandler(sys.stdout); info_handler.setLevel(logging.INFO); info_handler.addFilter(lambda r: r.levelno == logging.INFO); info_handler.setFormatter(formatter)
    err_handler = logging.StreamHandler(sys.stderr); err_handler.setLevel(logging.WARNING); err_handler.setFormatter(formatter)
    logger.addHandler(info_handler); logger.addHandler(err_handler)

    settings = _load_display_settings(logger)
    sub_addr = str(settings.get("sub_address", "tcp://127.0.0.1:5555"))
    zoom = int(settings.get("zoom", 8))
    poll_ms = int(settings.get("poll_ms", 5))

    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "aqua" in style.theme_names(): style.theme_use("aqua")
    except Exception: pass
        
    app = VirtualDisplay(root, sub_addr=sub_addr, zoom=zoom, poll_ms=poll_ms, logger=logger)
    if not root.winfo_exists(): return

    root.mainloop()

if __name__ == "__main__":
    main()
