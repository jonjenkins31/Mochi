"""Integrated MScript editor tab, ported from Mochi 3.0's Tk tool.

Two views of ONE document. The text editor and the node graph both read
and write the `[Main]` section's lines, so switching between them is a
re-render rather than an import/export — there is no second format to
keep in sync, and Save, Play, Resources and the live preview do not know
which view produced the text.

The language reference lives with the engine that executes it, in
JaegerAnimation (`jaeger_animation/docs/MSCRIPT.md`). This file knows the
document's SHAPE — sections, resources, one command per line — and
deliberately not what any command means.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from jaeger_os import topics

from modules import jaeger_animation as animation


_SECTION = re.compile(
    r"^\[\s*([A-Za-z_][\w-]*)\s+(start|end)\s*\]$", re.IGNORECASE,
)
_RESOURCE = re.compile(r"^\s*(K\[\d+\])\s*:\s*(['\"])(.*?)\2\s*$")
#: One `KEY[value]` pair. The same rule the engine's parser uses, which
#: is why `LBL[1]` and `JMP LBL[1]` both read correctly.
_ARG = re.compile(r"([A-Z_]+)\[([^\]]*)\]")
_FRAME = topics.ACT_DISPLAY_FRAME
_STATE = topics.ACT_DISPLAY_STATE


def parse_mscript(text: str) -> dict[str, list[str]]:
    """Split an MScript document into named sections without losing lines."""
    sections: dict[str, list[str]] = {"_header": []}
    current = "_header"
    for line in text.splitlines():
        match = _SECTION.match(line.strip())
        if match:
            name, boundary = match.groups()
            current = name.lower() if boundary.lower() == "start" else "_footer"
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def parse_resources(lines: list[str]) -> list[tuple[str, str]]:
    resources: list[tuple[str, str]] = []
    for line in lines:
        match = _RESOURCE.match(line)
        if match:
            resources.append((match.group(1), match.group(3)))
    return resources


@dataclass
class Step:
    """One line of `[Main]`, as both views understand it.

    `raw` is the line exactly as written, and it is what gets saved. A
    step nobody edited therefore round-trips byte for byte — including
    comments, blank lines, spacing and any command this app has never
    heard of. `retype()` is the only thing that regenerates it, so an
    unopened file cannot be quietly reformatted by being looked at in
    the node view.
    """

    command: str                      # "" for a comment or a blank line
    args: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    @property
    def is_note(self) -> bool:
        return not self.command

    def label(self) -> int | None:
        """The id this step declares (`LBL[1]`) or jumps to (`JMP LBL[1]`).

        The `:name` half is a comment — the engine strips it, so the
        graph has to as well or a wire to `LBL[1:top]` never draws.
        """
        if self.command not in ("LBL", "JMP"):
            return None
        try:
            return int(str(self.args.get("LBL", "")).split(":", 1)[0].strip())
        except ValueError:
            return None

    def retype(self, command: str, args: dict[str, str]) -> None:
        self.command = command
        self.args = dict(args)
        self.raw = render_step(command, args)


def render_step(command: str, args: dict[str, str]) -> str:
    """A command and its arguments as one canonical line.

    `LBL` writes its id onto the command token (`LBL[1]`) because that
    is the documented spelling; everything else keeps them apart
    (`JMP LBL[1]`, `BITMAP K[1] D[2.0]`). Both parse identically — the
    difference is only what a reader expects to see.
    """
    rest = {k: v for k, v in args.items() if not (command == "LBL" and k == "LBL")}
    head = f"{command}[{args['LBL']}]" if command == "LBL" and "LBL" in args else command
    return " ".join([head, *(f"{k}[{v}]" for k, v in rest.items())])


def parse_steps(lines: list[str]) -> list[Step]:
    """Read `[Main]` as a list of steps, losing nothing.

    Comments and blank lines become steps too. Dropping them would make
    the node view a lossy importer: open a script, switch views, save,
    and the author's notes are gone.
    """
    steps: list[Step] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("!"):
            steps.append(Step(command="", raw=line))
            continue
        head = stripped.split(maxsplit=1)[0]
        steps.append(Step(
            command=head.split("[", 1)[0].upper(),
            args=dict(_ARG.findall(stripped)),
            raw=line,
        ))
    return steps


def build_steps(steps: list[Step]) -> str:
    """The `[Main]` body those steps describe."""
    return "\n".join(step.raw for step in steps)


def build_mscript(
    main: str,
    resources: list[tuple[str, str]],
    *,
    header: list[str] | None = None,
    footer: list[str] | None = None,
) -> str:
    """Create the canonical two-section document used by Mochi 3.0/5."""
    output = list(header or [])
    if output and output[-1] != "":
        output.append("")
    output.extend(["[Main start]", *main.rstrip("\n").splitlines(), "[Main end]", ""])
    output.append("[Resources start]")
    output.extend(f"{resource_id}: '{path}'" for resource_id, path in resources)
    output.extend(["[Resources end]"])
    if footer:
        output.extend(["", *footer])
    return "\n".join(output).rstrip() + "\n"


class MscriptEditorTab:
    """A native Qt tab for editing and playing ``.mscript`` files."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui, self._QtWidgets = QtCore, QtGui, QtWidgets
        self.bus = app.bus
        self.project_root = pathlib.Path(__file__).resolve().parent.parent
        self.current_path: pathlib.Path | None = None
        self.character = None
        self.scripts_dir: pathlib.Path | None = None
        self.sections: dict[str, list[str]] = {}
        self.resources: list[tuple[str, str]] = []
        self._loading = False
        self._script_picker_loading = False
        self._frame = None
        self._status_text: str | None = None

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QtWidgets.QHBoxLayout()
        for label, callback in (
            ("New Motion…", self.new_character_script),
            ("Open…", self.open_script),
            ("Save", self.save_script),
            ("Save As…", self.save_script_as),
            ("Play", self.play_script),
            ("Stop", lambda: animation.stop(self.bus)),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            toolbar.addWidget(button)
        toolbar.addSpacing(12)
        toolbar.addWidget(QtWidgets.QLabel("Character motion"))
        self.script_box = QtWidgets.QComboBox()
        self.script_box.setMinimumWidth(220)
        self.script_box.currentIndexChanged.connect(self._script_picked)
        toolbar.addWidget(self.script_box)
        toolbar.addStretch(1)
        self.view_text = QtWidgets.QPushButton("Text")
        self.view_nodes = QtWidgets.QPushButton("Nodes")
        for button in (self.view_text, self.view_nodes):
            button.setCheckable(True)
            button.setAutoExclusive(True)
            toolbar.addWidget(button)
        self.view_text.setChecked(True)
        self.view_text.clicked.connect(lambda: self.show_view(0))
        self.view_nodes.clicked.connect(lambda: self.show_view(1))
        layout.addLayout(toolbar)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        layout.addWidget(splitter, 1)

        editor_group = QtWidgets.QGroupBox("Main")
        editor_layout = QtWidgets.QVBoxLayout(editor_group)
        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.editor.setTabStopDistance(32)
        # Two views, one document. The stack holds the SAME `[Main]`
        # lines; switching re-renders rather than importing, so nothing
        # below this point — save, play, resources, preview — has to know
        # which one the operator was last looking at.
        from .mscript_graph import MscriptGraph

        self.graph = MscriptGraph(on_changed=self._graph_edited)
        self.views = QtWidgets.QStackedWidget()
        self.views.addWidget(self.editor)
        self.views.addWidget(self.graph)
        editor_layout.addWidget(self.views)
        splitter.addWidget(editor_group)

        resource_group = QtWidgets.QGroupBox("Resources")
        resource_layout = QtWidgets.QVBoxLayout(resource_group)
        self.resource_list = QtWidgets.QListWidget()
        self.resource_list.itemDoubleClicked.connect(lambda _item: self.edit_resource())
        resource_layout.addWidget(self.resource_list, 1)
        buttons = QtWidgets.QHBoxLayout()
        for label, callback in (
            ("Add…", self.add_resource),
            ("Edit…", self.edit_resource),
            ("Remove", self.remove_resource),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        resource_layout.addLayout(buttons)
        splitter.addWidget(resource_group)
        splitter.addWidget(self._build_preview())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        splitter.setSizes([540, 270, 290])

        self.status = QtWidgets.QLabel("New script")
        layout.addWidget(self.status)
        self.editor.document().modificationChanged.connect(self._modified)
        self.bus.subscribe(_FRAME, self._on_frame)
        self.bus.subscribe(_STATE, self._on_state)
        self._preview_timer = QtCore.QTimer(self.widget)
        self._preview_timer.timeout.connect(self._repaint_preview)
        self._preview_timer.start(16)

    def _build_preview(self):
        QtCore, QtWidgets = self._QtCore, self._QtWidgets
        group = QtWidgets.QGroupBox("Live preview")
        layout = QtWidgets.QVBoxLayout(group)
        self.preview = QtWidgets.QLabel("Play a motion to preview it")
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumSize(220, 220)
        self.preview.setStyleSheet("background:#000; border:1px solid #33333f;")
        layout.addWidget(self.preview, 1)
        self.preview_state = QtWidgets.QLabel()
        self.preview_state.setWordWrap(True)
        self.preview_state.setStyleSheet("color:#777784;")
        layout.addWidget(self.preview_state)
        return group

    # ── two views of one document ────────────────────────────────
    #
    # The text editor IS the document. The graph is a rendering of it
    # that writes back, which is why every other method here — save,
    # play, the character picker — still just reads `self.editor` and
    # never asks which view is on top.

    def show_view(self, index: int) -> None:
        if index == 1:
            self.graph.set_text(self.editor.toPlainText())
        self.views.setCurrentIndex(index)

    def _refresh_view(self) -> None:
        """Re-render the graph when the document was replaced under it."""
        if self.views.currentIndex() == 1:
            self.graph.set_text(self.editor.toPlainText())

    def _graph_edited(self) -> None:
        self.editor.setPlainText(self.graph.text())
        self.editor.document().setModified(True)

    def _modified(self, modified: bool) -> None:
        if self._loading:
            return
        name = self.current_path.name if self.current_path else "new script"
        self.status.setText(f"{'Modified — ' if modified else ''}{name}")

    def _initial_dir(self) -> str:
        if self.scripts_dir is not None:
            return str(self.scripts_dir)
        path = self.project_root / "assets" / "mscripts"
        return str(path if path.is_dir() else self.project_root)

    def set_character(self, character: Any) -> bool:
        """Discover and offer the motion scripts owned by a character pack."""
        if self.editor.document().isModified() and not self._confirm_discard():
            return False
        self.character = character
        manifest = yaml.safe_load(
            (character.root / "character.yaml").read_text(encoding="utf-8")) or {}
        motion = manifest.get("motion_scripts") or {}
        self.scripts_dir = character.root / str(motion.get("root", "mscripts"))
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        default_value = str(motion.get("default", ""))
        default_path = character.root / default_value if default_value else None
        self._refresh_character_scripts(default_path)
        if self.script_box.count():
            path = pathlib.Path(str(self.script_box.currentData()))
            self.load_path(path)
        else:
            self.new_script()
            self.status.setText(
                f"{character.display_name or character.name}: no motion scripts yet")
        return True

    def _refresh_character_scripts(
        self, preferred: pathlib.Path | None = None,
    ) -> None:
        self._script_picker_loading = True
        self.script_box.clear()
        selected = 0
        scripts = sorted(self.scripts_dir.glob("*.mscript")) if self.scripts_dir else []
        for index, path in enumerate(scripts):
            self.script_box.addItem(path.stem.replace("_", " "), str(path))
            if preferred is not None and path.resolve() == preferred.resolve():
                selected = index
        if scripts:
            self.script_box.setCurrentIndex(selected)
        self._script_picker_loading = False

    def _script_picked(self, index: int) -> None:
        if self._script_picker_loading or index < 0:
            return
        if not self._confirm_discard():
            if self.current_path is not None:
                old_index = self.script_box.findData(str(self.current_path))
                if old_index >= 0:
                    self._script_picker_loading = True
                    self.script_box.setCurrentIndex(old_index)
                    self._script_picker_loading = False
            return
        self.load_path(pathlib.Path(str(self.script_box.itemData(index))))

    def _confirm_discard(self) -> bool:
        if not self.editor.document().isModified():
            return True
        result = self._QtWidgets.QMessageBox.question(
            self.widget,
            "Unsaved changes",
            "Discard the current unsaved changes?",
            self._QtWidgets.QMessageBox.Yes | self._QtWidgets.QMessageBox.No,
            self._QtWidgets.QMessageBox.No,
        )
        return result == self._QtWidgets.QMessageBox.Yes

    def new_script(self) -> None:
        if not self._confirm_discard():
            return
        self._loading = True
        self.current_path = None
        self.sections = {}
        self.resources = []
        self.editor.clear()
        self.editor.document().setModified(False)
        self._refresh_resources()
        self._refresh_view()
        self.status.setText("New script")
        self._loading = False

    def new_character_script(self) -> None:
        """Name a new motion and stage it in the selected character pack."""
        if not self._confirm_discard():
            return
        if self.scripts_dir is None:
            self.new_script()
            return
        default_name = "new_motion"
        name, accepted = self._QtWidgets.QInputDialog.getText(
            self.widget, "New character motion", "Motion name:",
            text=default_name)
        if not accepted:
            return
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
        if not slug:
            self._QtWidgets.QMessageBox.warning(
                self.widget, "Invalid name", "Enter a name for the motion.")
            return
        path = self.scripts_dir / f"{slug}.mscript"
        if path.exists():
            self._QtWidgets.QMessageBox.warning(
                self.widget, "Motion exists", f"{path.name} already exists.")
            return
        self._loading = True
        self.current_path = path
        display = self.character.display_name or self.character.name
        self.sections = {"_header": [f"! {display} motion: {name.strip()}"]}
        self.resources = []
        self.editor.clear()
        self.editor.document().setModified(True)
        self._refresh_resources()
        self._refresh_view()
        self.status.setText(f"New motion — {path}")
        self._loading = False

    def open_script(self) -> None:
        if not self._confirm_discard():
            return
        filename, _ = self._QtWidgets.QFileDialog.getOpenFileName(
            self.widget,
            "Open MScript",
            self._initial_dir(),
            "MochiScript (*.mscript);;All files (*)",
        )
        if filename:
            self.load_path(pathlib.Path(filename))

    def load_path(self, path: pathlib.Path) -> None:
        try:
            sections = parse_mscript(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            self._QtWidgets.QMessageBox.critical(
                self.widget, "Open failed", str(exc))
            return
        self._loading = True
        self.current_path = path
        self.sections = sections
        self.resources = parse_resources(sections.get("resources", []))
        self.editor.setPlainText("\n".join(sections.get("main", [])))
        self.editor.document().setModified(False)
        self._refresh_resources()
        self._refresh_view()
        self.status.setText(str(path))
        self._loading = False
        if self.scripts_dir is not None and path.parent.resolve() == self.scripts_dir.resolve():
            index = self.script_box.findData(str(path))
            if index >= 0:
                self._script_picker_loading = True
                self.script_box.setCurrentIndex(index)
                self._script_picker_loading = False

    def save_script(self) -> bool:
        return self._write(self.current_path) if self.current_path else self.save_script_as()

    def save_script_as(self) -> bool:
        filename, _ = self._QtWidgets.QFileDialog.getSaveFileName(
            self.widget,
            "Save MScript",
            str((self.current_path or pathlib.Path(self._initial_dir()) / "script.mscript")),
            "MochiScript (*.mscript)",
        )
        if not filename:
            return False
        path = pathlib.Path(filename)
        if not path.suffix:
            path = path.with_suffix(".mscript")
        return self._write(path)

    def _write(self, path: pathlib.Path | None) -> bool:
        if path is None:
            return False
        content = build_mscript(
            self.editor.toPlainText(),
            self.resources,
            header=self.sections.get("_header"),
            footer=self.sections.get("_footer"),
        )
        try:
            path.write_text(content, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._QtWidgets.QMessageBox.critical(
                self.widget, "Save failed", str(exc))
            return False
        self.current_path = path
        self.sections = parse_mscript(content)
        self.editor.document().setModified(False)
        self.status.setText(f"Saved {path}")
        if self.scripts_dir is not None and path.parent.resolve() == self.scripts_dir.resolve():
            self._refresh_character_scripts(path)
        return True

    def play_script(self) -> None:
        if self.editor.document().isModified() or self.current_path is None:
            if not self.save_script():
                return
        animation.play_file(self.bus, self.current_path, loop=False)
        self.status.setText(f"Playing {self.current_path.name}")
        self.preview_state.setText(f"Playing {self.current_path.name}")

    def _on_frame(self, msg: Any) -> None:
        if not msg.data or msg.width <= 0 or msg.height <= 0:
            return
        image = self._QtGui.QImage(
            bytes(msg.data), msg.width, msg.height, msg.width * 4,
            self._QtGui.QImage.Format_RGBA8888,
        )
        self._frame = image.copy()

    def _on_state(self, msg: Any) -> None:
        reason = getattr(msg, "reason", "")
        if reason:
            self._status_text = reason

    def _repaint_preview(self) -> None:
        if self._status_text:
            self.preview_state.setText(self._status_text)
            self._status_text = None
        if self._frame is None:
            return
        self.preview.setPixmap(self._QtGui.QPixmap.fromImage(self._frame).scaled(
            self.preview.size(), self._QtCore.Qt.KeepAspectRatio,
            self._QtCore.Qt.FastTransformation))

    def _refresh_resources(self) -> None:
        self.resource_list.clear()
        self.resource_list.addItems(
            [f"{resource_id}: '{path}'" for resource_id, path in self.resources]
        )

    def _next_resource_id(self) -> str:
        used = []
        for resource_id, _path in self.resources:
            match = re.fullmatch(r"K\[(\d+)\]", resource_id)
            if match:
                used.append(int(match.group(1)))
        return f"K[{max(used, default=0) + 1}]"

    def _resource_dialog(self, current: tuple[str, str]) -> tuple[str, str] | None:
        QtWidgets = self._QtWidgets
        dialog = QtWidgets.QDialog(self.widget)
        dialog.setWindowTitle("MScript Resource")
        form = QtWidgets.QFormLayout(dialog)
        id_edit = QtWidgets.QLineEdit(current[0])
        path_edit = QtWidgets.QLineEdit(current[1])
        browse = QtWidgets.QPushButton("Browse…")
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(path_edit, 1)
        path_row.addWidget(browse)
        form.addRow("ID", id_edit)
        form.addRow("Path", path_row)
        actions = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)

        def choose() -> None:
            start = self.current_path.parent if self.current_path else pathlib.Path(self._initial_dir())
            filename, _ = QtWidgets.QFileDialog.getOpenFileName(
                dialog, "Select resource", str(start), "All files (*)")
            if not filename:
                return
            selected = pathlib.Path(filename)
            # MScript playback resolves resource paths from the project root,
            # regardless of whether the script lives in assets/mscripts/ or
            # inside a character pack.
            base = self.project_root
            try:
                value = selected.relative_to(base).as_posix()
            except ValueError:
                value = str(selected)
            path_edit.setText(value)

        browse.clicked.connect(choose)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return None
        resource_id, resource_path = id_edit.text().strip(), path_edit.text().strip()
        if not re.fullmatch(r"K\[\d+\]", resource_id) or not resource_path:
            QtWidgets.QMessageBox.warning(
                self.widget, "Invalid resource", "Use an ID such as K[1] and a file path.")
            return None
        return resource_id, resource_path

    def add_resource(self) -> None:
        result = self._resource_dialog((self._next_resource_id(), ""))
        if result:
            self.resources.append(result)
            self._refresh_resources()
            self.editor.document().setModified(True)

    def edit_resource(self) -> None:
        row = self.resource_list.currentRow()
        if row < 0:
            return
        result = self._resource_dialog(self.resources[row])
        if result:
            self.resources[row] = result
            self._refresh_resources()
            self.resource_list.setCurrentRow(row)
            self.editor.document().setModified(True)

    def remove_resource(self) -> None:
        row = self.resource_list.currentRow()
        if row < 0:
            return
        del self.resources[row]
        self._refresh_resources()
        self.editor.document().setModified(True)

    def close(self) -> None:
        try:
            self._preview_timer.stop()
            self.bus.unsubscribe(_FRAME, self._on_frame)
            self.bus.unsubscribe(_STATE, self._on_state)
        except Exception:  # noqa: BLE001
            pass


__all__ = [
    "MscriptEditorTab", "build_mscript", "parse_mscript", "parse_resources",
]
