"""Window gallery and quarantined launchers for every pre-v5 GUI.

Current-bus replacements open in-process. Original Mochi 3.0/v4 windows remain
launchable in isolated subprocesses so their layouts are available during the
later consolidation pass without mixing their obsolete transports into v5.
"""

from __future__ import annotations

from dataclasses import dataclass
import pathlib
import subprocess
import sys
from typing import Any, Callable

from PySide6 import QtCore, QtWidgets

from .media_player import FloatingMediaPlayer
from .performance import PerformanceWindow
from .popup_player import PopupPlayerController
from .virtual_display import VirtualDisplayWindow


@dataclass(frozen=True)
class LegacyWindowSpec:
    generation: str
    id: str
    name: str
    source: pathlib.Path
    command: tuple[str, ...]
    note: str = "old transport; visual reference"


def legacy_window_specs(root: pathlib.Path) -> tuple[LegacyWindowSpec, ...]:
    v3 = root / "archive" / "mochi-3.0"
    v4 = root / "archive" / "mochi-v4"
    specs: list[LegacyWindowSpec] = []
    v4_launch = {
        "companion": "Companion / nine-page Studio",
        "player": "Skinnable virtual-display player",
        "chat": "LLM chat window",
        "perf": "Performance monitor",
        "animation": "Animation control panel",
        "vdisplay": "Virtual LED display",
        "viewer": "Floating image viewer",
    }
    launch_file = v4 / "mochi" / "interfaces" / "v4" / "launch.py"
    for window_id, name in v4_launch.items():
        specs.append(LegacyWindowSpec(
            "Mochi v4", f"v4-{window_id}", name, launch_file,
            ("-m", "mochi.interfaces.v4.launch", window_id)))
    specs.extend((
        LegacyWindowSpec(
            "Mochi v4", "v4-studio", "Studio window",
            v4 / "mochi/interfaces/studio/__main__.py",
            ("-m", "mochi.interfaces.studio")),
        LegacyWindowSpec(
            "Mochi v4", "v4-media", "Standalone media player",
            v4 / "mochi/interfaces/media_player/__main__.py",
            ("-m", "mochi.interfaces.media_player")),
    ))
    v3_files = {
        "control": ("Control panel", "gui/mochi_gui.py"),
        "display": ("Virtual LED display", "gui/mochi_vdisplay.py"),
        "popup-tk": ("Popup player (Tk)", "gui/mochi_vdisplay_player.py"),
        "popup-qt": ("Popup player (Qt)", "gui/mochi_vdisplay_player_qt.py"),
        "perf": ("Performance monitor", "gui/mochi_perf.py"),
        "chat": ("LLM chat window", "gui/llm_chat_gui.py"),
        "studio": ("Mochi Studio", "tools/mochi_studio.py"),
        "bitmap": ("Bitmap editor", "tools/bitmap_editor_gui.py"),
        "mscript": ("MScript editor", "tools/mscript_editor_gui.py"),
        "sprite": ("Sprite editor", "tools/sprite_editor_gui.py"),
    }
    for window_id, (name, relative) in v3_files.items():
        source = v3 / relative
        specs.append(LegacyWindowSpec(
            "Mochi 3.0", f"v3-{window_id}", name, source,
            (str(source),)))
    # Only offer what is still on disk. Every window here has a v5 tab that
    # replaces it, so when an archive generation is deleted its rows should
    # disappear rather than become buttons that cannot start anything.
    return tuple(spec for spec in specs if spec.source.is_file())


class WindowManager:
    """Own every additional current window opened from the main app."""

    def __init__(self, app: Any) -> None:
        self.root = pathlib.Path(getattr(app, "root", pathlib.Path.cwd())).resolve()
        self.popup = PopupPlayerController(app)
        self.media = FloatingMediaPlayer(self.root)
        self.virtual_display = VirtualDisplayWindow(app.bus)
        self.performance = PerformanceWindow(app)

    def close(self) -> None:
        self.popup.close()
        self.media.shutdown()
        self.virtual_display.shutdown()
        self.performance.shutdown()


class LegacyWindowsTab:
    """One place to open restored windows and inspect every archived one."""

    def __init__(self, app: Any, qt: tuple, manager: WindowManager) -> None:
        _QtCore, _QtGui, QtWidgets_ = qt
        self.manager = manager
        self.root = manager.root
        self._processes: list[subprocess.Popen] = []
        #: row -> the process launched from it, while it is still being
        #: watched. Dropped once it has reported an exit code.
        self._watched: dict[int, subprocess.Popen] = {}
        self.widget = QtWidgets_.QWidget()
        outer = QtWidgets_.QVBoxLayout(self.widget)
        outer.setContentsMargins(10, 10, 10, 10)

        current = QtWidgets_.QGroupBox("Restored current-bus windows")
        current_layout = QtWidgets_.QGridLayout(current)
        buttons: tuple[tuple[str, Callable[[], None]], ...] = (
            ("Open skinnable popup player", manager.popup.show),
            ("Popup player settings…", lambda: manager.popup.open_settings(self.widget)),
            ("Open floating media player", lambda: manager.media.show_player()),
            ("Open virtual LED display", manager.virtual_display.show_window),
            ("Open performance monitor", manager.performance.show_window),
        )
        for index, (label, callback) in enumerate(buttons):
            button = QtWidgets_.QPushButton(label)
            button.clicked.connect(callback)
            current_layout.addWidget(button, index // 2, index % 2)
        outer.addWidget(current)

        specs = legacy_window_specs(self.root)
        note = QtWidgets_.QLabel(
            "Original windows are intentionally kept separate for comparison. "
            "They open in isolated processes and still use their historical "
            "transport/configuration; use them as visual references until each "
            "is consolidated into the current bus."
            if specs else
            "No archived generation is present. Every window they held has a "
            "tab above — the editors live in Characters and MScript Editor.")
        note.setWordWrap(True); note.setStyleSheet("color:#8a8a98;")
        outer.addWidget(note)

        self.table = QtWidgets_.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Generation", "Window", "Source", "Status", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QtWidgets_.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setRowCount(len(specs))
        for row, spec in enumerate(specs):
            self.table.setItem(row, 0, QtWidgets_.QTableWidgetItem(spec.generation))
            self.table.setItem(row, 1, QtWidgets_.QTableWidgetItem(spec.name))
            try:
                shown = str(spec.source.relative_to(self.root))
            except ValueError:
                shown = str(spec.source)
            self.table.setItem(row, 2, QtWidgets_.QTableWidgetItem(shown))
            self.table.setItem(row, 3, QtWidgets_.QTableWidgetItem("reference"))
            launch = QtWidgets_.QPushButton("Launch original")
            launch.clicked.connect(lambda _=False, item=spec, r=row:
                                   self._launch(item, r))
            self.table.setCellWidget(row, 4, launch)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QtWidgets_.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets_.QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.table, 1)

        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._poll)
        self._timer.start(500)

    def _launch(self, spec: LegacyWindowSpec, row: int) -> None:
        cwd = (self.root / "archive" / "mochi-v4"
               if spec.generation == "Mochi v4"
               else self.root / "archive" / "mochi-3.0")
        try:
            process = subprocess.Popen([sys.executable, *spec.command], cwd=str(cwd))
        except OSError as exc:
            self.table.item(row, 3).setText(f"failed: {exc}")
            return
        self._processes.append(process)
        self._watched[row] = process
        self.table.item(row, 3).setText(f"starting (pid {process.pid})…")

    def _poll(self) -> None:
        """Say whether the window SURVIVED, not whether Popen returned.

        These launch archived v4 code in a separate interpreter, and the
        commonest outcome is a process that exits before it draws
        anything — a missing dependency, an old transport, a `main()`
        that rejects its own arguments. Reporting "launched (pid N)" the
        instant Popen returns made every one of those look like a window
        that opened and then hid: the tab claimed success for a process
        that was already dead. An exit code is the useful half of the
        answer, so it is what gets shown.
        """
        for row, process in list(self._watched.items()):
            code = process.poll()
            if code is None:
                self.table.item(row, 3).setText(f"running (pid {process.pid})")
                continue
            del self._watched[row]
            self.table.item(row, 3).setText(
                "closed" if code == 0 else
                f"exited({code}) — see the terminal for why")

    def close(self) -> None:
        self._timer.stop()
        # Reference processes intentionally survive independently; they are
        # comparison windows, not children on the current app bus.
        self._processes = [p for p in self._processes if p.poll() is None]


__all__ = [
    "LegacyWindowSpec", "legacy_window_specs", "WindowManager",
    "LegacyWindowsTab",
]
