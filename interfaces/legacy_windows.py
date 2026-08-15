"""Window gallery and quarantined launchers for every pre-v5 GUI.

Current-bus replacements open in-process. Original Mochi 3.0/v4 windows remain
launchable in isolated subprocesses so their layouts are available during the
later consolidation pass without mixing their obsolete transports into v5.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
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


#: What an archived window may need that this app's venv does not have.
#: The Mochi 3.0 GUIs are Tk, and one of them uses an f-string with a
#: backslash — legal from Python 3.12, a SyntaxError before it. Neither
#: is a reason to add tkinter to a PySide6 app's requirements.
_LEGACY_NEEDS = "import _tkinter, PySide6"


def _interpreter(generation: str = "") -> str:
    """A python that can actually run this window, or ours if none can.

    Split by GENERATION because the two eras want opposite things. The
    Mochi 3.0 GUIs are Tk and this app's venv has no `_tkinter`, plus
    one of them needs 3.12+ to parse at all — they need the outside
    interpreter. The v4 windows are PySide6 and run happily in our venv;
    pointing them at the outside one instead traded a working window for
    a dylib that only resolves in here.

    Probed once and cached: the answer cannot change while we run.
    """
    global _CACHED_INTERPRETER
    if not generation.startswith("Mochi 3"):
        return sys.executable
    if _CACHED_INTERPRETER is not None:
        return _CACHED_INTERPRETER
    candidates = [sys.executable]
    candidates += [p for name in ("python3.13", "python3.12", "python3")
                   if (p := shutil.which(name))]
    candidates.append("/usr/bin/python3")
    for candidate in candidates:
        try:
            probe = subprocess.run(
                [candidate, "-c", _LEGACY_NEEDS],
                capture_output=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            _CACHED_INTERPRETER = candidate
            return candidate
    _CACHED_INTERPRETER = sys.executable
    return _CACHED_INTERPRETER


_CACHED_INTERPRETER: str | None = None


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
    # JaegerAI's avatar surfaces. Not an archive and not a Mochi module —
    # a sibling product whose UI is under review before anything is kept.
    # Launched through dev/tools/jaeger_ai_windows.py, which puts that
    # source on the path rather than installing it, so looking at a
    # design costs nothing and commits to nothing.
    launcher = root / "dev" / "tools" / "jaeger_ai_windows.py"
    if launcher.is_file() and (pathlib.Path.home() / "GITHUB" / "JaegerAI").is_dir():
        for window_id, name in (
            ("orb", "VoiceOrb — reactive voice ring"),
            ("player", "Floating avatar player"),
            ("avatar", "Avatar view (the panel alone)"),
            ("chat", "Avatar + chat — the composed surface"),
        ):
            specs.append(LegacyWindowSpec(
                "JaegerAI", f"jai-{window_id}", name, launcher,
                (str(launcher), window_id),
                note="sibling product; under review"))

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

    def __init__(self, app: Any, character_of: Any = None) -> None:
        self.root = pathlib.Path(getattr(app, "root", pathlib.Path.cwd())).resolve()
        self.app = app
        #: How every avatar surface asks which pack is loaded, so a
        #: window opened before a character swap still scales right.
        self.character_of = character_of
        # The two keepers, built on first open. A CharacterView is one
        # subscription and cheap; AvatarChatWindow builds a whole second
        # ChatTab, and a conversation nobody asked to see should not be
        # subscribing to anything.
        self.character_view: Any = None
        self.avatar_chat: Any = None
        self.popup = PopupPlayerController(app)
        self.media = FloatingMediaPlayer(self.root)
        self.virtual_display = VirtualDisplayWindow(app.bus)
        self.performance = PerformanceWindow(app)

    def show_character_view(self) -> None:
        from .character_view import CharacterView
        if self.character_view is None:
            self.character_view = CharacterView(
                self.app, character_of=self.character_of)
        self.character_view.show_window()

    def show_avatar_chat(self) -> None:
        from .avatar_chat import AvatarChatWindow
        if self.avatar_chat is None:
            self.avatar_chat = AvatarChatWindow(
                self.app, character_of=self.character_of)
        self.avatar_chat.show_window()

    def close(self) -> None:
        for window in (self.character_view, self.avatar_chat):
            if window is not None:
                window.shutdown()
        self.popup.close()
        self.media.shutdown()
        self.virtual_display.shutdown()
        self.performance.shutdown()


def _environment(cwd: pathlib.Path) -> dict[str, str]:
    """PYTHONPATH the archived tools were written to assume.

    The 3.0 editors import `animations` and `core.mscript_engine` as
    top-level packages, which worked when they ran from a tree that had
    both on the path. In the archive they live under
    plugins/animation_node/, so the imports fail and the window dies
    before drawing. Handing them the path is cheaper and less invasive
    than editing archived source to find itself.
    """
    env = dict(os.environ)
    extra = [str(cwd), str(cwd / "plugins" / "animation_node")]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join([*extra, existing] if existing else extra)
    return env


def _why(log: Any) -> str:
    """The last thing a dead window said, for the Status column."""
    try:
        log.close()
        lines = [ln.strip() for ln in
                 pathlib.Path(log.name).read_text(errors="replace").splitlines()
                 if ln.strip()]
        pathlib.Path(log.name).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 — a status string is never worth raising
        return "see the terminal"
    return (lines[-1][:120] if lines else "no output")


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

        current = QtWidgets_.QGroupBox("Windows")
        current_layout = QtWidgets_.QGridLayout(current)
        buttons: tuple[tuple[str, Callable[[], None]], ...] = (
            # The two chosen surfaces first — everything below them is a
            # variation on the same frames that has not been cut yet.
            ("Open character view", manager.show_character_view),
            ("Open character + chat", manager.show_avatar_chat),
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
            "Archived Mochi windows and JaegerAI's avatar surfaces, side by "
            "side with what replaced them. "
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
        cwd = {
            "Mochi v4": self.root / "archive" / "mochi-v4",
            "Mochi 3.0": self.root / "archive" / "mochi-3.0",
        }.get(spec.generation, self.root)
        # Keep the child's output. These die on a missing asset or an
        # import the archive no longer contains, and "exited(1)" sends
        # the reader to a terminal they were not watching — the reason
        # is one line and belongs in the row that reports the failure.
        log = tempfile.NamedTemporaryFile(
            mode="w+", suffix=".log", prefix=f"mochi-{spec.id}-", delete=False)
        try:
            process = subprocess.Popen(
                [_interpreter(spec.generation), *spec.command], cwd=str(cwd),
                stdout=log, stderr=subprocess.STDOUT, env=_environment(cwd))
        except OSError as exc:
            log.close()
            self.table.item(row, 3).setText(f"failed: {exc}")
            return
        self._processes.append(process)
        self._watched[row] = (process, log)
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
        for row, (process, log) in list(self._watched.items()):
            code = process.poll()
            if code is None:
                self.table.item(row, 3).setText(f"running (pid {process.pid})")
                continue
            del self._watched[row]
            self.table.item(row, 3).setText(
                "closed" if code == 0 else f"exited({code}) — {_why(log)}")

    def close(self) -> None:
        self._timer.stop()
        # Reference processes intentionally survive independently; they are
        # comparison windows, not children on the current app bus.
        self._processes = [p for p in self._processes if p.poll() is None]


__all__ = [
    "LegacyWindowSpec", "legacy_window_specs", "WindowManager",
    "LegacyWindowsTab",
]
