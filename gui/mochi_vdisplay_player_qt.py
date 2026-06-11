"""
mochi_vdisplay_player_qt.py
---------------------------

Qt-based overlay that displays a PNG (with full per-pixel alpha) in a frameless,
transparent window. This uses PySide6 so the image can truly float above the
desktop without a solid background.

Usage:
    python gui/mochi_vdisplay_player_qt.py \
        --image plugins/animation_node/assets/video/player/tv1.png \
        --scale 1.0 \
        --opacity 1.0 \
        --topmost \
        --sub tcp://127.0.0.1:5555

Click and drag anywhere on the overlay to move it (disable with --no-drag).
Press Esc/Q or right-click to close.
"""

from __future__ import annotations

import argparse
import logging
import struct
import sys
from pathlib import Path

import yaml
import zmq

try:
    import PySide6
    from PySide6.QtCore import Qt, QPoint, QTimer
    from PySide6.QtGui import QGuiApplication, QImage, QPixmap
    from PySide6.QtWidgets import QApplication, QLabel, QWidget
except ImportError as exc:  # pragma: no cover - optional dependency
    raise SystemExit(
        "PySide6 is required for this viewer. Install it with:\n"
        "    python -m pip install PySide6"
    ) from exc


DEFAULT_IMAGE = Path("assets/video/player/tv1.png")
DEFAULT_SCREEN_BBOX = (425, 289, 150, 150)  # left, top, width, height for tv1 artwork

GUI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = GUI_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from transport import make_node_topics

HEADER_FMT = ">HHQI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
CONFIG_PATHS = [
    PROJECT_ROOT / "config.yaml",
    PROJECT_ROOT / "plugins" / "animation_node" / "config.yaml",
]
DEFAULT_SUB_ADDRESS = "tcp://127.0.0.1:5555"
DEFAULT_NODE_ID = "animation"
DEFAULT_POLL_MS = 10


def _load_profiles(logger: logging.Logger | None = None) -> tuple[dict, dict[str, dict]]:
    defaults: dict = {}
    profiles: dict[str, dict] = {}
    for path in CONFIG_PATHS:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            continue
        except yaml.YAMLError as exc:
            if logger:
                logger.warning("Failed to parse %s: %s", path, exc)
            continue
        except Exception as exc:
            if logger:
                logger.warning("Failed to read %s: %s", path, exc)
            continue

        default_section = data.get("display_player") or {}
        if isinstance(default_section, dict):
            defaults.update(default_section)

        players_section = data.get("display_players") or {}
        if isinstance(players_section, dict):
            for name, cfg in players_section.items():
                if not isinstance(cfg, dict):
                    continue
                profiles.setdefault(str(name), {}).update(cfg)

    return defaults, profiles


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Display a PNG in a translucent Qt window.")
    parser.add_argument(
        "--image",
        help="Path to the PNG image (must contain alpha for transparent regions).",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=None,
        help="Optional scale multiplier for the image size (default 1.0).",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=None,
        help="Window opacity (0.0 - 1.0). Defaults to 1.0 (fully opaque).",
    )
    parser.add_argument(
        "--topmost",
        dest="topmost",
        action="store_true",
        help="Force the window to stay on top.",
    )
    parser.add_argument(
        "--no-topmost",
        dest="topmost",
        action="store_false",
        help="Prevent the window from staying on top.",
    )
    parser.set_defaults(topmost=None)
    parser.add_argument(
        "--no-drag",
        action="store_true",
        help="Disable click-and-drag behaviour (enabled by default).",
    )
    parser.add_argument(
        "--profile",
        help="Player profile name defined in config.yaml (display_players section).",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available player profiles and exit.",
    )
    parser.add_argument(
        "--sub",
        help="ZMQ SUB address for the animation node frames.",
    )
    parser.add_argument(
        "--node-id",
        help="Node ID used to derive the ZMQ topics (default: animation).",
    )
    parser.add_argument(
        "--poll",
        type=int,
        help="Polling interval in milliseconds for incoming frames (default: 10).",
    )
    parser.add_argument(
        "--screen-bbox",
        help="Override the screen region as 'left,top,width,height' (defaults to artwork hint).",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable ZMQ streaming and only show the static artwork.",
    )
    return parser


def _parse_bbox(value: str | None) -> tuple[int, int, int, int] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        return None
    try:
        left, top, width, height = (int(p) for p in parts)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


class PlayerWindow(QWidget):
    def __init__(
        self,
        *,
        image_path: Path,
        scale: float,
        opacity: float,
        topmost: bool,
        screen_bbox: tuple[int, int, int, int] | None,
        sub_addr: str,
        node_id: str,
        poll_interval: int,
        stream_enabled: bool,
        logger: logging.Logger | None,
        enable_drag: bool = True,
    ) -> None:
        super().__init__()

        # Configure window flags/attributes for a transparent, frameless overlay.
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        if topmost:
            self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setWindowOpacity(max(0.0, min(1.0, opacity)))

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            raise ValueError(f"Unable to load image: {image_path}")
        if scale != 1.0:
            new_width = max(1, int(pixmap.width() * scale))
            new_height = max(1, int(pixmap.height() * scale))
            pixmap = pixmap.scaled(
                new_width,
                new_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        label = QLabel(self)
        label.setPixmap(pixmap)
        label.setAttribute(Qt.WA_TranslucentBackground, True)
        label.setStyleSheet("background: transparent; border: 0;")
        self.background_label = label
        self.background_pixmap = pixmap
        self.resize(pixmap.size())
        self.setFocusPolicy(Qt.ClickFocus)

        bbox = screen_bbox or DEFAULT_SCREEN_BBOX
        scaled_bbox = (
            int(bbox[0] * scale),
            int(bbox[1] * scale),
            int(bbox[2] * scale),
            int(bbox[3] * scale),
        )
        left, top, width, height = scaled_bbox
        self.screen_label = QLabel(self)
        self.screen_label.setGeometry(left, top, width, height)
        self.screen_label.setStyleSheet("background-color: black; border: 0;")
        self.screen_label.setAlignment(Qt.AlignCenter)
        self.screen_label.raise_()

        self.logger = logger
        self.stream_enabled = stream_enabled
        self.enable_drag = enable_drag
        self._drag_offset: QPoint | None = None
        self._frame_bytes: bytes | None = None
        self._screen_pixmap: QPixmap | None = None

        self._timer = None
        self._socket = None
        self._ctx = None
        self._topics = None
        self._poll_interval = max(1, int(poll_interval))
        self._screen_size = (width, height)

        if self.stream_enabled:
            try:
                self._ctx = zmq.Context.instance()
                self._socket = self._ctx.socket(zmq.SUB)
                self._socket.setsockopt(zmq.LINGER, 0)
                self._socket.setsockopt(zmq.RCVHWM, 1)
                self._socket.connect(sub_addr)
                self._topics = make_node_topics(node_id)
                self._socket.setsockopt(zmq.SUBSCRIBE, self._topics.frame)
            except Exception as exc:
                if self.logger:
                    self.logger.error("Failed to initialise ZMQ stream: %s", exc)
                self.stream_enabled = False
                if self._socket is not None:
                    try:
                        self._socket.close(0)
                    except Exception:
                        pass
                    self._socket = None
            else:
                self._timer = QTimer(self)
                self._timer.setInterval(self._poll_interval)
                self._timer.timeout.connect(self._poll_stream)
                self._timer.start()

    # ------------------------------------------------------------------ interaction
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.raise_()
            self.setFocus(Qt.ActiveWindowFocusReason)
            if self.enable_drag:
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
        elif event.button() == Qt.RightButton:
            self.close()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.enable_drag and self._drag_offset is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ streaming
    def _poll_stream(self):
        if not self._socket:
            return
        try:
            parts = self._socket.recv_multipart(flags=zmq.NOBLOCK)
        except zmq.Again:
            return
        except Exception as exc:
            if self.logger:
                self.logger.debug("ZMQ poll error: %s", exc)
            return

        if len(parts) < 2:
            return
        payload = parts[1]
        if len(payload) < HEADER_SIZE:
            return
        try:
            w, h, ts_ms, seq = struct.unpack_from(HEADER_FMT, payload, 0)
        except struct.error:
            return
        if w <= 0 or h <= 0:
            return
        rgb = memoryview(payload)[HEADER_SIZE:]
        expected = w * h * 3
        if len(rgb) != expected:
            return

        self._frame_bytes = bytes(rgb)
        image = QImage(self._frame_bytes, w, h, 3 * w, QImage.Format_RGB888)
        if image.isNull():
            return

        target_w, target_h = self._screen_size
        if target_w != w or target_h != h:
            image = image.scaled(target_w, target_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

        pixmap = QPixmap.fromImage(image)
        self._screen_pixmap = pixmap
        self.screen_label.setPixmap(pixmap)

    def closeEvent(self, event):
        if self._timer:
            self._timer.stop()
        if self._socket:
            try:
                self._socket.close(0)
            except Exception:
                pass
            self._socket = None
        super().closeEvent(event)


def _center_on_screen(widget: QWidget) -> None:
    screen = QGuiApplication.primaryScreen()
    if not screen:
        return
    geo = screen.availableGeometry()
    size = widget.frameGeometry()
    size.moveCenter(geo.center())
    widget.move(size.topLeft())


def main(argv: list[str] | None = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(argv)

    logger = logging.getLogger("MochiPlayerQt")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    plugin_root = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"  # type: ignore[name-defined]
    if plugin_root.exists():
        QApplication.setLibraryPaths([str(plugin_root)])

    defaults_cfg, profiles_cfg = _load_profiles(logger)

    if args.list_profiles:
        names = sorted(profiles_cfg.keys())
        if names:
            logger.info("Available profiles: %s", ", ".join(names))
        else:
            logger.info("No display player profiles defined in config files.")
        return 0

    profile_name = args.profile or next(iter(profiles_cfg), None)
    profile_data: dict = dict(defaults_cfg)
    if profile_name and profile_name in profiles_cfg:
        profile_data.update(profiles_cfg[profile_name])
    elif args.profile:
        logger.warning("Profile '%s' not found; using defaults.", args.profile)

    def _resolve_image(path_str: str | None) -> Path:
        candidate = Path(path_str) if path_str else DEFAULT_IMAGE
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        return candidate

    image_path = _resolve_image(args.image or profile_data.get("image"))
    if not image_path.exists():
        fallback = _resolve_image(str(DEFAULT_IMAGE))
        if fallback.exists():
            logger.warning("Image not found: %s; falling back to %s", image_path, fallback)
            image_path = fallback
        else:
            logger.error("Image not found: %s (no fallback available)", image_path)
            return 1

    scale = args.scale if args.scale is not None else float(profile_data.get("scale", 1.0))
    opacity = args.opacity if args.opacity is not None else float(profile_data.get("opacity", 1.0))

    screen_bbox = _parse_bbox(args.screen_bbox)
    if screen_bbox is None:
        cfg_bbox = profile_data.get("screen_bbox")
        if isinstance(cfg_bbox, (list, tuple)) and len(cfg_bbox) == 4:
            try:
                screen_bbox = tuple(int(v) for v in cfg_bbox)
            except (TypeError, ValueError):
                screen_bbox = DEFAULT_SCREEN_BBOX
        else:
            screen_bbox = DEFAULT_SCREEN_BBOX

    if args.topmost is not None:
        topmost = args.topmost
    else:
        topmost = bool(profile_data.get("topmost", False))

    drag_enabled = profile_data.get("drag", True)
    if args.no_drag:
        drag_enabled = False

    stream_cfg = profile_data.get("stream") if isinstance(profile_data.get("stream"), dict) else {}
    stream_enabled = stream_cfg.get("enabled", True)
    if args.no_stream:
        stream_enabled = False

    sub_addr = args.sub or stream_cfg.get("sub_address") or DEFAULT_SUB_ADDRESS
    node_id = args.node_id or stream_cfg.get("node_id") or DEFAULT_NODE_ID
    poll_interval = args.poll if args.poll is not None else int(stream_cfg.get("poll_ms", DEFAULT_POLL_MS))

    app = QApplication(sys.argv)

    try:
        window = PlayerWindow(
            image_path=image_path,
            scale=scale,
            opacity=opacity,
            topmost=topmost,
            screen_bbox=screen_bbox,
            sub_addr=sub_addr,
            node_id=node_id,
            poll_interval=poll_interval,
            stream_enabled=stream_enabled,
            logger=logger,
            enable_drag=drag_enabled,
        )
    except Exception as exc:
        logger.error("Failed to initialise overlay: %s", exc)
        return 1

    _center_on_screen(window)
    window.show()
    if stream_enabled:
        logger.info(
            "Displaying %s (scale %.2f, opacity %.2f) — streaming from %s",
            image_path,
            scale,
            opacity,
            sub_addr,
        )
    else:
        logger.info(
            "Displaying %s (scale %.2f, opacity %.2f) — static mode",
            image_path,
            scale,
            opacity,
        )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
