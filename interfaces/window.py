"""The window — a tab per thing you can watch.

    Face      the character, and the controls that drive it
    Voice     what the TTS is asked to say, and what came back
    Hearing   what the microphone hears, and what the STT made of it

Same shape as JP01-CC01's `interfaces/`: one file per tab, each a bus
subscriber that imports no engine. A tab works identically whether its
module is installed or not — with one it fills, without it stays empty
and says why. That is the composition being real rather than claimed.

The surface factory named by `jaeger.toml` lives here.
"""

from __future__ import annotations

import os
from typing import Any

_STYLE = """
QWidget { background:#101014; color:#c8c8d0;
          font-family:-apple-system,Segoe UI,sans-serif; font-size:12px; }
QPushButton { background:#1e1e26; border:1px solid #33333f;
              border-radius:4px; padding:5px 10px; }
QPushButton:hover { background:#2a2a34; }
QPushButton:checked { background:#3a5a8a; border-color:#4a7ab0; }
QComboBox, QLineEdit { background:#1e1e26; border:1px solid #33333f;
                       border-radius:4px; padding:4px 8px; }
QPlainTextEdit { background:#0b0b0e; border:1px solid #22222c;
                 border-radius:4px; font-family:ui-monospace,Menlo,monospace; }
QTabBar::tab { background:#16161c; padding:6px 14px; border:1px solid #22222c;
               border-bottom:none; }
QTabBar::tab:selected { background:#1e1e26; color:#e0e0e8; }
QTabWidget::pane { border:1px solid #22222c; }
QProgressBar { background:#0b0b0e; border:1px solid #22222c; border-radius:3px; }
QProgressBar::chunk { background:#4a7ab0; }
"""


def _qt():
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:  # pragma: no cover - env dependent
        raise RuntimeError(
            "Mochi's window needs PySide6 — the ecosystem's standard "
            "cross-platform GUI toolkit:\n    pip install pyside6"
        ) from exc
    return QtCore, QtGui, QtWidgets


class MochiWindow:
    """The tabbed shell. Owns nothing but layout and teardown."""

    def __init__(self, app: Any) -> None:
        qt = _qt()
        QtCore, QtGui, QtWidgets = qt

        from .hearing import HearingTab
        from .player import FaceTab
        from .voice import VoiceTab

        try:
            config = (app.config or {})
        except Exception:  # noqa: BLE001
            config = {}

        self.widget = QtWidgets.QTabWidget()
        self.widget.setStyleSheet(_STYLE)

        self.face = FaceTab(app, qt, config.get("player", {}) or {})
        self.voice = VoiceTab(app, qt)
        self.hearing = HearingTab(app, qt)
        self._tabs = (self.face, self.voice, self.hearing)

        self.widget.addTab(self.face.widget, "Face")
        self.widget.addTab(self.voice.widget, "Voice")
        self.widget.addTab(self.hearing.widget, "Hearing")

        self.widget.setWindowTitle(f"Mochi — {self.face.character.name}")
        scale = int(os.environ.get("MOCHI_SCALE",
                                   (config.get("player") or {}).get("scale", 2)))
        self.widget.resize(max(560, 256 * scale), 256 * scale + 130)

    def start(self) -> None:
        self.widget.show()
        self.face.start()

    def close(self) -> None:
        for tab in self._tabs:
            try:
                tab.close()
            except Exception:  # noqa: BLE001
                pass
        self.widget.close()


def make_player(app: Any, spec: Any) -> MochiWindow:
    """Surface factory named by ``jaeger.toml``."""
    window = MochiWindow(app)
    window.start()
    return window


__all__ = ["MochiWindow", "make_player"]
