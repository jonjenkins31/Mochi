"""Standalone media player (mochi-v4 style):

    python -m mochi.interfaces.media_player <path/to/image-gif-or-video>

With no path it opens empty; drop a file path to play it in a frameless,
draggable, always-on-top window (Esc / Q to dismiss).
"""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from mochi.interfaces.media_player.window import FloatingMediaPlayer

    app = QApplication(sys.argv)
    win = FloatingMediaPlayer()
    if len(sys.argv) > 1:
        win.play(sys.argv[1])
    else:
        win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
