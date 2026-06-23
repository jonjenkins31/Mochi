"""Picker to launch the quarantined v4 reference windows from the running app.

Each window runs as its OWN subprocess — its main() builds its own QApplication,
which would fight the running app's Qt loop if launched in-process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout,
)

from .launch import WINDOWS

_REPO = Path(__file__).resolve().parents[3]
_LABELS = {
    "companion": "Companion — the 9-page v4 Studio",
    "player": "Virtual-display player (native Qt)",
    "chat": "LLM chat",
    "perf": "Perf monitor",
    "animation": "Animation control panel",
    "vdisplay": "Virtual display",
    "viewer": "Image viewer (tk→qt)",
}


def launch_window(name: str) -> None:
    """Launch a v4 window in its own process (isolated Qt loop)."""
    subprocess.Popen(
        [sys.executable, "-m", "mochi.interfaces.v4.launch", name], cwd=str(_REPO)
    )


class V4Picker(QDialog):
    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reference windows (v4)")
        self.setMinimumWidth(320)
        v = QVBoxLayout(self)
        note = QLabel("Imported mochi-v4 windows — reference only.\n"
                      "They use the old bus, so most controls are inert.")
        note.setWordWrap(True)
        v.addWidget(note)
        for name in WINDOWS:
            b = QPushButton(_LABELS.get(name, name))
            b.clicked.connect(lambda _=False, n=name: launch_window(n))
            v.addWidget(b)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.close)
        v.addWidget(box)


def open_picker(parent: Any = None) -> V4Picker:
    dlg = V4Picker(parent)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg
