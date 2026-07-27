"""
mochi_vdisplay_player_tk2qt.py
------------------------------

A lightweight viewer that simply displays a PNG (or other Pillow-supported)
image in a borderless, transparent Qt (PySide6) window so that only the
artwork is visible.

This is a faithful 1:1 port of the original tkinter player
(archive/mochi-v4/interfaces/mochi_vdisplay_player.py): all non-UI logic
(argument parsing, image loading via Pillow, opacity / topmost handling,
window centering, close behavior) is preserved. Only the widget / layout /
event-loop layer was migrated from tkinter to PySide6.

Usage:
    python interfaces/v4/mochi_vdisplay_player_tk2qt.py \
        --image plugins/animation_node/assets/video/player/tv1.png \
        --opacity 1.0 \
        --topmost

Click anywhere on the window or press Esc/Q to close.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


DEFAULT_IMAGE = Path("plugins/animation_node/assets/video/player/tv1.png")


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Display a PNG as a transparent window.")
    parser.add_argument(
        "--image",
        default=str(DEFAULT_IMAGE),
        help="Path to the PNG (or other Pillow-supported image) to display.",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="Optional scaling factor for the image (default: 1.0).",
    )
    parser.add_argument(
        "--opacity",
        type=float,
        default=1.0,
        help="Window opacity (0.0 - 1.0). Defaults to 1.0 (fully opaque).",
    )
    parser.add_argument(
        "--topmost",
        action="store_true",
        help="Keep the window above other windows.",
    )
    return parser


def _load_pixmap(path: Path, scale: float) -> QPixmap:
    """
    Load ``path`` via Pillow (matching the original loader: RGBA + LANCZOS
    scaling) and convert the result into a Qt ``QPixmap`` for display.
    """
    image = Image.open(path).convert("RGBA")
    if scale != 1.0:
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)

    data = image.tobytes("raw", "RGBA")
    qimage = QImage(data, image.width, image.height, QImage.Format_RGBA8888)
    # Copy so the QImage owns its data once the Pillow buffer goes out of scope.
    return QPixmap.fromImage(qimage.copy())


class MochiVDisplayPlayerWindow(QWidget):
    """
    Borderless, transparent top-level window that shows a single image and
    closes on click / Esc / Q (the Qt equivalent of the original ``tk.Tk``
    root plus its image ``tk.Label``).
    """

    def __init__(
        self,
        image_path: Path | str | None = None,
        *,
        scale: float = 1.0,
        opacity: float = 1.0,
        topmost: bool = False,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__()

        self._logger = logger or logging.getLogger("MochiPlayerAsset")
        self._scale = scale

        # --- transparency / borderless (Qt equivalent of overrideredirect +
        # transparent bg attributes from _configure_transparency) ---
        flags = Qt.FramelessWindowHint
        if topmost:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # --- opacity (clamped exactly as the original) ---
        self.setWindowOpacity(max(0.0, min(1.0, opacity)))

        # --- image label ---
        self._label = QLabel(self)
        self._label.setContentsMargins(0, 0, 0, 0)
        self._label.setStyleSheet("background: transparent; border: 0px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._label)

        if image_path is not None:
            self.set_image(image_path, scale)

    # ------------------------------------------------------------------
    # image handling
    # ------------------------------------------------------------------
    def set_image(self, image_path: Path | str, scale: float | None = None) -> None:
        scale = self._scale if scale is None else scale
        pixmap = _load_pixmap(Path(image_path), scale)
        self._label.setPixmap(pixmap)
        self._label.resize(pixmap.width(), pixmap.height())
        self._center_window(pixmap.width(), pixmap.height())

    # ------------------------------------------------------------------
    # geometry (Qt equivalent of _center_window)
    # ------------------------------------------------------------------
    def _center_window(self, width: int, height: int) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.geometry()
            x = (geo.width() - width) // 2
            y = (geo.height() - height) // 2
            self.setGeometry(x, y, width, height)
        else:
            self.resize(width, height)

    # ------------------------------------------------------------------
    # close behavior: click anywhere, Esc, or 'q'
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt name)
        if event.button() == Qt.LeftButton:
            self.close()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt name)
        if event.key() == Qt.Key_Escape or event.key() == Qt.Key_Q:
            self.close()
        else:
            super().keyPressEvent(event)


def main(argv: list[str] | None = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(argv)

    logger = logging.getLogger("MochiPlayerAsset")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    image_path = Path(args.image)
    if not image_path.is_absolute():
        image_path = (Path(__file__).resolve().parent.parent / image_path).resolve()
    if not image_path.exists():
        logger.error("Image not found: %s", image_path)
        return 1

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])

    try:
        window = MochiVDisplayPlayerWindow(
            image_path,
            scale=args.scale,
            opacity=args.opacity,
            topmost=args.topmost,
            logger=logger,
        )
    except Exception as exc:
        logger.error("Failed to load image '%s': %s", image_path, exc)
        return 1

    logger.info("Displaying %s (scale=%.2f)", image_path, args.scale)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
