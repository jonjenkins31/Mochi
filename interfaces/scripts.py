"""Scripts tab — every premade script, one button each.

The Stage tab is a rig: pickers, a game, a text box, a character you
drive by hand. This is the opposite and that is why it is separate — a
list of things that are already written, and a button that runs one.

    characters/<id>/mscripts/*.mscript    the loaded character's own
    assets/mscripts/*.mscript             the engine demos, shared

Only scripts the CONDUCTOR can run are listed. A file with no FACE, SAY
or LISTEN in it is an animation the engine plays, not a performance —
`core/scenes.py` already draws that line and this tab just believes it,
rather than offering a button that does nothing visible.

IT TAKES THE FACE WHILE IT RUNS. A script saying "this is what
searching looks like" must not be repainted two seconds later by the
mind going idle, so `AgentFace` is held for the duration and handed
back — repainting at once — when the script ends or is stopped.
"""

from __future__ import annotations

import pathlib
from typing import Any

from core import scenes


def catalogue(character: Any, root: pathlib.Path,
              demos: bool = False) -> list:
    """(scene, where) — this character's scripts, and optionally the
    engine's demos.

    THE DEMOS ARE OFF BY DEFAULT and that is the whole point of the
    flag. `assets/mscripts/` is a set of ENGINE demonstrations: they
    play test bitmaps, timers, and in four cases another pack's sprite
    sheet outright. Listing `demo sprite Patric Sprite` under Crazy Eyes
    is offering to play a different character, which is what it looked
    like — a list of things that had nothing to do with the one on
    screen.

    They are still reachable, because they are the best examples of the
    asset commands that exist. They are just not this character's.
    """
    found = [(scene, "character") for scene in scenes.available(character)]
    if not demos:
        return found
    seen = {scene.path for scene, _ in found}
    for path in sorted((root / "assets" / "mscripts").glob("*.mscript")):
        if path in seen:
            continue
        try:
            scene = scenes.load(path)
        except Exception:  # noqa: BLE001 — a broken file is not a broken tab
            continue
        if scenes.performable(scene):
            found.append((scene, "engine demo"))
    return found


class ScriptsTab:
    """Run a written performance and watch it happen."""

    def __init__(self, app: Any, qt: tuple, character_of: Any,
                 face: Any = None) -> None:
        QtCore, _QtGui, QtWidgets = qt
        self._QtCore, self._QtWidgets = QtCore, QtWidgets
        self.app = app
        self.character_of = character_of
        self.face = face
        self.runner: Any = None
        self._lines: list[str] = []

        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.widget)
        root.setContentsMargins(10, 10, 10, 10)

        head = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel()
        head.addWidget(self.title)
        head.addStretch(1)
        self.demos = QtWidgets.QCheckBox("engine demos")
        self.demos.setToolTip(
            "also list assets/mscripts/ — demonstrations of the asset "
            "commands, which play test assets and other characters' "
            "artwork rather than this one's")
        self.demos.toggled.connect(lambda _on: self.reload())
        head.addWidget(self.demos)
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        self.stop_btn = QtWidgets.QPushButton("■ Stop")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        head.addWidget(refresh)
        head.addWidget(self.stop_btn)
        root.addLayout(head)

        split = QtWidgets.QHBoxLayout()
        self.list = QtWidgets.QListWidget()
        self.list.setMinimumWidth(300)
        self.list.itemDoubleClicked.connect(lambda _i: self.run())
        self.list.currentRowChanged.connect(self._describe)
        split.addWidget(self.list, 2)

        side = QtWidgets.QVBoxLayout()
        self.detail = QtWidgets.QLabel("pick a script.")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("color:#777784;")
        self.detail.setAlignment(QtCore.Qt.AlignTop)
        side.addWidget(self.detail)
        self.run_btn = QtWidgets.QPushButton("▶  Run")
        self.run_btn.clicked.connect(self.run)
        side.addWidget(self.run_btn)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setPlaceholderText("what the script is doing appears here.")
        side.addWidget(self.log, 1)
        split.addLayout(side, 3)
        root.addLayout(split, 1)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color:#777784;")
        root.addWidget(self.status)

        self.entries: list = []
        self.reload()
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._drain)
        self._timer.start(120)

    # ── the list ─────────────────────────────────────────────────

    def reload(self) -> None:
        """Rebuild from disk. Cheap, and the alternative is editing a
        script and wondering why the button still runs the old one."""
        character = self._character()
        self.title.setText(
            f"Scripts for {getattr(character, 'display_name', '—')}"
            if character else "Scripts")
        self.list.clear()
        self.entries = catalogue(
            character, pathlib.Path(getattr(self.app, "root", ".")),
            demos=self.demos.isChecked()) if character else []
        root = pathlib.Path(getattr(self.app, "root", "."))
        for scene, where in self.entries:
            if where != "character":
                self.list.addItem(f"{scene.name}  ·  {where}")
                continue
            # A script in a sub-folder shows which one. Ten shorts and
            # three demos in one flat list is a list you have to read.
            folder = scene.path.parent.name
            self.list.addItem(f"{folder} / {scene.name}"
                              if folder != "mscripts" else scene.name)
        if self.entries:
            self.list.setCurrentRow(0)
        else:
            self.detail.setText(
                "this character has no scripts of its own.\n\n"
                "Tick 'engine demos' for the shared examples, or write one "
                "into its mscripts/ folder.")

    def _character(self) -> Any:
        try:
            return self.character_of()
        except Exception:  # noqa: BLE001
            return None

    def _describe(self, row: int) -> None:
        if not (0 <= row < len(self.entries)):
            return
        scene, where = self.entries[row]
        kinds: dict[str, int] = {}
        for step in scene.steps:
            kinds[step.kind] = kinds.get(step.kind, 0) + 1
        parts = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        self.detail.setText(
            f"{scene.description}\n\n{len(scene.steps)} steps — {parts}\n"
            f"{scene.path.name}  ({where})")

    # ── running ──────────────────────────────────────────────────

    def run(self) -> None:
        row = self.list.currentRow()
        character = self._character()
        if not (0 <= row < len(self.entries)) or character is None:
            return
        self.stop()
        scene = self.entries[row][0]
        # The script owns the face until it is done, so the agent's own
        # state does not paint over a line about what searching looks
        # like.
        if self.face is not None:
            self.face.hold(True)
        self.log.clear()
        self.runner = scenes.SceneRunner(
            self.app, character, on_event=self._lines.append)
        self.runner.start(scene)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status.setText(f"running {scene.name}")

    def stop(self) -> None:
        if self.runner is not None:
            self.runner.stop()
            self.runner = None
        self._release()

    def _release(self) -> None:
        if self.face is not None:
            self.face.hold(False)
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _drain(self) -> None:
        while self._lines:
            self.log.appendPlainText(self._lines.pop(0))
        if self.runner is not None and not self.runner.running:
            self.runner = None
            self._release()
            self.status.setText("done.")

    def close(self) -> None:
        self._timer.stop()
        self.stop()


__all__ = ["ScriptsTab", "catalogue"]
