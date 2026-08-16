"""The window — a tab per thing you can watch.

    Face      the character, and the controls that drive it
    Windows   popup/media/virtual-display/performance windows + legacy gallery
    Chat      talk to the mind, and watch one turn happen
    Voice     what the TTS is asked to say, and what came back
    Assets    every playable file, previewed by the engine itself
    Hearing   what the microphone hears, and what the STT made of it
    Stage     drive a character: scenes, expressions, a line to the mind
    Vision    what the camera sees

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
QWidget { background:#101014; color:#c8c8d0; font-size:12px; }
QPushButton { background:#1e1e26; border:1px solid #33333f;
              border-radius:4px; padding:5px 10px; }
QPushButton:hover { background:#2a2a34; }
QPushButton:checked { background:#3a5a8a; border-color:#4a7ab0; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
                       background:#1e1e26; border:1px solid #33333f;
                       border-radius:4px; padding:4px 8px; }
QPlainTextEdit { background:#0b0b0e; border:1px solid #22222c;
                 border-radius:4px; font-family:ui-monospace,Menlo,monospace; }
QListWidget, QTreeWidget, QTableWidget, QGraphicsView {
                       background:#0b0b0e; border:1px solid #22222c; }
QHeaderView::section { background:#1e1e26; color:#c8c8d0;
                       border:1px solid #33333f; padding:4px; }
QGroupBox { border:1px solid #2a2a34; border-radius:4px;
            margin-top:8px; padding-top:8px; }
QGroupBox::title { subcontrol-origin:margin; left:8px; padding:0 4px; }
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

        from .assets import AssetsTab
        from .character_editor import CharacterEditorTab
        from .chat import ChatTab
        from .hearing import HearingTab
        from .mscript_editor import MscriptEditorTab
        from .modules import ModulesTab
        from .cast import CastTab
        from .legacy_windows import LegacyWindowsTab, WindowManager
        from .player import FaceTab, _roster
        from .runtime import RuntimeTab
        from .scripts import ScriptsTab
        from .stage import StageTab
        from .vision import VisionTab
        from .voice import VoiceTab

        try:
            config = (app.config or {})
        except Exception:  # noqa: BLE001
            config = {}

        self.widget = QtWidgets.QTabWidget()
        self.widget.setStyleSheet(_STYLE)

        self.face = FaceTab(app, qt, config.get("player", {}) or {})
        self.window_manager = WindowManager(
            app, character_of=lambda: self.face.character)
        # The roster, as cards. Selecting routes through the Face tab's
        # pack box — the one code path that loads a character — so the
        # display, the persona and the voice all move together and this
        # tab never has to know they exist.
        self.cast = CastTab(
            app, qt, _roster(), on_select=self.face.pack_box.setCurrentText,
            active=self.face.character.name)
        # Whoever changed it, the cards follow. Connected after the Face
        # tab's own slot, so `face.character` is already the new one.
        self.face.pack_box.currentTextChanged.connect(self.cast.set_active)
        self.face.avatar_btn.clicked.connect(self.open_avatar)
        # The face follows what the agent is DOING, for packs that have
        # words for it. Lives here rather than in a tab because it must
        # keep working with this window shut, which is the normal case.
        from core.agent_face import AgentFace
        self.agent_face = AgentFace(app, lambda: self.face.character)
        self.window_manager.face = self.agent_face
        manager = self.window_manager
        self.window_manager.menu = (
            ("Operator window", "Ctrl+1", self.open_operator),
            ("-", "", None),
            ("Skinnable popup player", "", manager.popup.show),
            ("Virtual LED display", "", manager.virtual_display.show_window),
            ("Performance monitor", "", manager.performance.show_window),
        )
        self.face.popup_btn.clicked.connect(self.window_manager.popup.show)
        self.mscript_editor = MscriptEditorTab(app, qt)
        self.character_editor = CharacterEditorTab(
            app, qt, self.face.character.name,
            on_character_changed=self.mscript_editor.set_character)
        self.assets = AssetsTab(app, qt)
        self.modules = ModulesTab(app, qt)
        self.runtime = RuntimeTab(
            app, qt, self.window_manager.performance.show_window)
        self.stage = StageTab(app, qt)
        # After agent_face, because the tab suspends it while a script
        # runs — a script cannot own the face without something to
        # take it from.
        self.scripts = ScriptsTab(
            app, qt, lambda: self.face.character, self.agent_face)
        self.face.pack_box.currentTextChanged.connect(
            lambda _n: self.scripts.reload())
        self.windows = LegacyWindowsTab(app, qt, self.window_manager)
        self.chat = ChatTab(app, qt, lambda: self.face.character)
        self.voice = VoiceTab(app, qt)
        self.hearing = HearingTab(app, qt)
        self.vision = VisionTab(app, qt)
        self._tabs = (
            self.face, self.cast, self.character_editor, self.mscript_editor,
            self.assets,
            self.modules,
            self.runtime, self.scripts, self.stage, self.windows, self.chat, self.voice, self.hearing,
            self.vision,
        )

        self.widget.addTab(self.face.widget, "Face")
        self.widget.addTab(self.cast.widget, "Cast")
        self.widget.addTab(self.character_editor.widget, "Characters")
        self.widget.addTab(self.mscript_editor.widget, "MScript Editor")
        self.widget.addTab(self.assets.widget, "Assets")
        self.widget.addTab(self.modules.widget, "Modules")
        self.widget.addTab(self.runtime.widget, "Runtime")
        self.widget.addTab(self.scripts.widget, "Scripts")
        self.widget.addTab(self.stage.widget, "Stage")
        self.widget.addTab(self.windows.widget, "Windows")
        self.widget.addTab(self.chat.widget, "Chat")
        self.widget.addTab(self.voice.widget, "Voice")
        self.widget.addTab(self.hearing.widget, "Hearing")
        self.widget.addTab(self.vision.widget, "Vision")

        # ONE OWNER OF THE DISPLAY AT A TIME. The Face tab walks its
        # character's expressions on a timer; the Stage drives a
        # performance. Both publish to /act/display/play, so with both
        # live the screen alternates between two characters' artwork —
        # which is what "it keeps flicking between designs" was.
        #
        # A background tab has no business driving the display, so
        # cycling pauses whenever the Face tab is not the visible one.
        self.widget.currentChanged.connect(self._tab_changed)

        self.widget.setWindowTitle(f"Mochi — {self.face.character.name}")
        scale = int(os.environ.get("MOCHI_SCALE",
                                   (config.get("player") or {}).get("scale", 2)))
        self.widget.resize(max(1100, 256 * scale), max(720, 256 * scale + 130))

    def _tab_changed(self, index: int) -> None:
        showing_face = self.widget.widget(index) is self.face.widget
        if not showing_face and self.face.cycle_btn.isChecked():
            self._cycle_was_on = True
            self.face.cycle_btn.setChecked(False)
        elif showing_face and getattr(self, "_cycle_was_on", False):
            self._cycle_was_on = False
            self.face.cycle_btn.setChecked(True)

    def open_avatar(self) -> None:
        """The primary window — what launching Mochi opens."""
        self.window_manager.show_avatar()

    def open_operator(self) -> None:
        """This tabbed window: settings, editors, switches, everything
        that runs the character rather than being it. Reached from the
        avatar window's File menu, because that is the front door now."""
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()

    def start(self) -> None:
        # The AVATAR window is what launching Mochi opens. This tabbed
        # one is the operator's and comes up on request — from its File
        # menu, or `main.py --operator` for a session spent in here.
        self.face.start()
        if os.environ.get("MOCHI_OPERATOR"):
            self.open_operator()
        self.open_avatar()

    def close(self) -> None:
        for tab in self._tabs:
            try:
                tab.close()
            except Exception:  # noqa: BLE001
                pass
        self.agent_face.close()
        self.window_manager.close()
        self.widget.close()


def make_player(app: Any, spec: Any) -> MochiWindow:
    """Surface factory named by ``jaeger.toml``."""
    window = MochiWindow(app)
    window.start()
    return window


__all__ = ["MochiWindow", "make_player"]
