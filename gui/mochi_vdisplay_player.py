"""
mochi_vdisplay_player.py
------------------------

A lightweight viewer that simply displays a PNG (or other Pillow-supported)
image in a borderless, transparent Tk window so that only the artwork is visible.

Usage:
    python gui/mochi_vdisplay_player.py \
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

import tkinter as tk
from PIL import Image, ImageTk


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


def _load_image(path: Path, scale: float, *, master: tk.Misc | None = None) -> ImageTk.PhotoImage:
    image = Image.open(path).convert("RGBA")
    if scale != 1.0:
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)
    return ImageTk.PhotoImage(image, master=master)


def _configure_transparency(root: tk.Tk, logger: logging.Logger) -> str:
    """
    Best-effort configuration of a transparent window across platforms.
    """
    try:
        root.overrideredirect(True)
    except Exception as exc:
        logger.debug("overrideredirect failed: %s", exc)

    try:
        # macOS / some X11 environments
        root.wm_attributes("-transparent", True)
        root.configure(bg="systemTransparent")
        return "systemTransparent"
    except Exception:
        pass

    try:
        # Windows / X11 fallback using a chroma key
        transparent_color = "#010203"
        root.configure(bg=transparent_color)
        root.wm_attributes("-transparentcolor", transparent_color)
        return transparent_color
    except Exception as exc:
        logger.debug("transparentcolor attribute not supported: %s", exc)
        root.configure(bg="black")
        return "black"


def _center_window(root: tk.Tk, width: int, height: int) -> None:
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    root.geometry(f"{width}x{height}+{x}+{y}")


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

    root = tk.Tk()
    bg_color = _configure_transparency(root, logger)
    try:
        photo = _load_image(image_path, args.scale, master=root)
    except Exception as exc:
        logger.error("Failed to load image '%s': %s", image_path, exc)
        root.destroy()
        return 1
    try:
        root.wm_attributes("-alpha", max(0.0, min(1.0, args.opacity)))
    except Exception as exc:
        logger.debug("Opacity attribute not supported: %s", exc)

    if args.topmost:
        try:
            root.wm_attributes("-topmost", True)
        except Exception as exc:
            logger.debug("Topmost attribute not supported: %s", exc)

    label_bg = bg_color if bg_color else "black"
    label = tk.Label(root, image=photo, borderwidth=0, highlightthickness=0, bg=label_bg)
    label.pack()

    _center_window(root, photo.width(), photo.height())

    def close_window(_event=None):
        root.destroy()

    root.bind("<Escape>", close_window)
    root.bind("q", close_window)
    label.bind("<Button-1>", close_window)

    logger.info("Displaying %s (scale=%.2f)", image_path, args.scale)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
