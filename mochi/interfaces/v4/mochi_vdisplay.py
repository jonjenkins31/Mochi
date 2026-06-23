# mochi_vdisplay.py — Minimal Virtual LED Display (PySide6 / Qt)
# This client receives small, logical frames and performs a pixel-perfect upscale.
#
# Qt port of the original Tkinter virtual display.  All non-UI logic (zmq
# subscribing, frame decoding, FPS accounting, polling cadence) is preserved
# 1:1; only the widget / layout / event-loop layer changed.

import struct
import time
from pathlib import Path

from PIL import Image, ImageQt
import yaml
import logging
import sys
import zmq

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

# --- Protocol & transport (must match mochi_node.py) ---
HEADER_FMT = ">HHQI"   # w,h,uint64 ts_ms,uint32 seq
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# The root directory of the Mochi project.
GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
CONFIG_PATHS = [
    PROJECT_ROOT / "config.yaml",
    PROJECT_ROOT / "plugins" / "animation_node" / "config.yaml",
]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from transport import make_node_topics


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
        if "sub_address" not in settings and node_cfg.get("pub_address"):
            settings["sub_address"] = node_cfg["pub_address"]

        if "node_id" not in settings and node_cfg.get("id"):
            settings["node_id"] = str(node_cfg["id"])

        # If we already have everything we need, stop searching.
        if {"sub_address", "zoom", "poll_ms"} <= settings.keys():
            break

    settings.setdefault("sub_address", "tcp://127.0.0.1:5555")
    settings.setdefault("zoom", 8)
    settings.setdefault("poll_ms", 5)
    settings.setdefault("node_id", "animation")
    return settings


class VirtualDisplay(QMainWindow):
    def __init__(self, sub_addr: str, zoom: int, poll_ms: int, node_id: str, logger):
        super().__init__()
        self.logger = logger
        self.poll_ms = int(max(1, poll_ms))
        self.zoom = int(max(1, zoom))
        self.node_id = node_id
        self.topics = make_node_topics(node_id)

        self.setWindowTitle("Mochi Virtual Display — Qt")

        self._closed = False

        # --- Central layout: image area on top, status bar on bottom ---
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.img_label = QLabel(central)
        self.img_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.img_label, stretch=1)

        self.status_bar = QFrame(central)
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(8, 0, 8, 0)
        self.status_label = QLabel("", self.status_bar)
        self.fps_label = QLabel("FPS: --", self.status_bar)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch(1)
        status_layout.addWidget(self.fps_label)
        layout.addWidget(self.status_bar)

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
            self._closed = True
            QTimer.singleShot(0, self.close)
            return

        frame_topic = self.topics.frame
        self.sub.setsockopt(zmq.SUBSCRIBE, frame_topic)
        self.status_label.setText(
            f"SUB -> {sub_addr} topic='{frame_topic.decode()}'  |  q/Esc to quit"
        )

        self._last_t = time.time()
        self._frames = 0

        # Repeating poll loop — the Qt equivalent of root.after(poll_ms, poll).
        self._timer = QTimer(self)
        self._timer.setInterval(self.poll_ms)
        self._timer.timeout.connect(self.poll)
        self._timer.start()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Q, Qt.Key_Escape):
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._closed = True
        timer = getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()
        sub = getattr(self, "sub", None)
        if sub is not None:
            try:
                sub.close(0)
            except Exception:
                pass
        super().closeEvent(event)

    def _lock_to_image(self, dw: int, dh: int):
        try:
            sb_h = self.status_bar.sizeHint().height() if self.status_bar.isVisible() else 0
            total_w, total_h = dw, dh + sb_h
            self.setFixedSize(total_w, total_h)
        except Exception as e:
            self.logger.warning(f"Failed to lock window size: {e}")

    def poll(self):
        if self._closed:
            return
        try:
            topic, payload = self.sub.recv_multipart(flags=zmq.NOBLOCK)
        except zmq.Again:
            return
        except Exception as e:
            self.status_label.setText(f"ZMQ error: {e}")
            return

        if len(payload) < HEADER_SIZE:
            return
        try:
            w, h, ts_ms, seq = struct.unpack_from(HEADER_FMT, payload, 0)
        except struct.error:
            return

        rgb_mv = memoryview(payload)[HEADER_SIZE:]
        expected = w * h * 3
        if w <= 0 or h <= 0 or len(rgb_mv) != expected:
            return

        im_logical = Image.frombuffer("RGB", (w, h), rgb_mv, "raw", "RGB", 0, 1)

        dw, dh = w * self.zoom, h * self.zoom
        if self.zoom > 1:
            im_display = im_logical.resize((dw, dh), resample=Image.NEAREST)
        else:
            im_display = im_logical

        self.photo = QPixmap.fromImage(ImageQt.ImageQt(im_display))
        self.img_label.setPixmap(self.photo)
        if self._disp_size != (dw, dh):
            self._disp_size = (dw, dh)
            self._lock_to_image(dw, dh)

        self._frames += 1
        now = time.time()
        if now - self._last_t >= 1.0:
            fps = self._frames / (now - self._last_t)
            self.fps_label.setText(f"FPS: {fps:.1f}")
            self._frames = 0
            self._last_t = now

        self.status_label.setText(f"seq={seq}  {w}x{h} -> {dw}x{dh}  ts={ts_ms}")


def main(argv=None) -> int:
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
    node_id = str(settings.get("node_id", "animation"))

    app = QApplication.instance() or QApplication(sys.argv if argv is None else [sys.argv[0], *argv])

    app_window = VirtualDisplay(
        sub_addr=sub_addr,
        zoom=zoom,
        poll_ms=poll_ms,
        node_id=node_id,
        logger=logger,
    )
    if app_window._closed:
        return 0

    app_window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
