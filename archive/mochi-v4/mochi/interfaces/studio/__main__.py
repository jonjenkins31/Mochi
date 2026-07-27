"""Preview Mochi Studio with no bus / model / instance:

    python -m mochi.interfaces.studio
"""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from mochi.interfaces.studio.window import MochiStudioWindow

    app = QApplication(sys.argv)
    win = MochiStudioWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
