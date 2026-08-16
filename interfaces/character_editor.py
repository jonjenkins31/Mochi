"""Character-pack configuration, asset routing, and engine preview UI."""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from typing import Any

from jaeger_os import topics

from modules import jaeger_animation as animation
from .bitmap_editor import BitmapEditorTab
from .sprite_editor import SpriteEditorTab


_FRAME = topics.ACT_DISPLAY_FRAME
_STATE = topics.ACT_DISPLAY_STATE


def character_asset_rows(character: Any) -> list[dict[str, Any]]:
    """Flatten a manifest's expression mapping for the asset inspector."""
    rows: list[dict[str, Any]] = []
    for expression, spec in character.expressions.items():
        adapter = str(spec.get("adapter", character.adapter))
        default_asset = str(spec.get("asset", character.render["asset"]))

        if character.kind == "sprite_sheet":
            states = list(character.mouth_states) or [""]
            for state in states:
                if "src" in spec:
                    address = "SRC[{}]".format(
                        ", ".join(str(value) for value in spec["src"]))
                elif "cell" in spec:
                    address = f"cell {int(spec['cell'])}"
                else:
                    column = int(spec.get("column", 0))
                    state_row = int(character.mouth_states.get(state, 0))
                    columns = character.grid[0] if character.grid else 1
                    address = f"cell {state_row * columns + column}"
                rows.append({
                    "expression": expression,
                    "state": state,
                    "adapter": adapter,
                    "address": address,
                    "asset": default_asset,
                    "exists": (character.root / default_asset).is_file(),
                })
            continue

        clips = spec.get("clips")
        if isinstance(clips, Mapping):
            states = list(character.mouth_states) or list(clips)
            for state in states:
                asset = str(clips.get(state) or clips.get("default") or "")
                rows.append({
                    "expression": expression,
                    "state": state,
                    "adapter": adapter,
                    "address": "clip",
                    "asset": asset,
                    "exists": bool(asset) and (character.root / asset).is_file(),
                })
        else:
            asset = str(clips or default_asset)
            rows.append({
                "expression": expression,
                "state": "",
                "adapter": adapter,
                "address": "params" if character.kind == "procedural" else "clip",
                "asset": asset,
                "exists": bool(asset) and (character.root / asset).is_file(),
            })
    return rows


class AssetMappingPane:
    """A readable map of states to files/cells for non-atlas characters."""

    def __init__(self, qt: tuple, play_callback: Any) -> None:
        QtCore, _QtGui, QtWidgets = qt
        self._QtCore, self._QtWidgets = QtCore, QtWidgets
        self._play_callback = play_callback
        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.heading = QtWidgets.QLabel()
        self.heading.setObjectName("Heading")
        layout.addWidget(self.heading)
        help_text = QtWidgets.QLabel(
            "Double-click a row to render it through the animation engine. "
            "Edit paths, adapters, states, and expressions in Config."
        )
        help_text.setWordWrap(True)
        help_text.setObjectName("Dim")
        layout.addWidget(help_text)

        self.table = QtWidgets.QTreeWidget()
        self.table.setHeaderLabels(
            ["Expression", "State", "Adapter", "Address", "Asset", "File"])
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(self._play_item)
        layout.addWidget(self.table, 1)

        play = QtWidgets.QPushButton("Preview selected")
        play.clicked.connect(self._play_selected)
        layout.addWidget(play, 0, QtCore.Qt.AlignRight)

    def set_character(self, character: Any) -> None:
        self.heading.setText(
            f"{character.display_name or character.name} — "
            f"{character.adapter} {character.kind.replace('_', ' ')}"
        )
        self.table.clear()
        for row in character_asset_rows(character):
            item = self._QtWidgets.QTreeWidgetItem([
                row["expression"], row["state"], row["adapter"],
                row["address"], row["asset"], "found" if row["exists"] else "MISSING",
            ])
            item.setData(0, self._QtCore.Qt.UserRole, row["expression"])
            item.setData(1, self._QtCore.Qt.UserRole, row["state"])
            if not row["exists"]:
                item.setForeground(5, self._QtCore.Qt.red)
            self.table.addTopLevelItem(item)
        for column in range(4):
            self.table.resizeColumnToContents(column)
        if self.table.topLevelItemCount():
            self.table.setCurrentItem(self.table.topLevelItem(0))

    def _play_item(self, item: Any, _column: int = 0) -> None:
        self._play_callback(
            item.data(0, self._QtCore.Qt.UserRole),
            item.data(1, self._QtCore.Qt.UserRole),
        )

    def _play_selected(self) -> None:
        item = self.table.currentItem()
        if item is not None:
            self._play_item(item)


class CharacterPreviewPane:
    """Preview every character type using the real animation bus."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui, self._QtWidgets = QtCore, QtGui, QtWidgets
        self.bus = app.bus
        self.character = None
        self._frame = None
        self._status_text: str | None = None

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.screen = QtWidgets.QLabel("Choose an expression and press Play")
        self.screen.setAlignment(QtCore.Qt.AlignCenter)
        self.screen.setMinimumSize(320, 300)
        self.screen.setObjectName("Screen")
        layout.addWidget(self.screen, 1)

        controls = QtWidgets.QHBoxLayout()
        self.expression_box = QtWidgets.QComboBox()
        self.state_box = QtWidgets.QComboBox()
        self.play_button = QtWidgets.QPushButton("Play")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.play_button.clicked.connect(self.play)
        self.stop_button.clicked.connect(lambda: animation.stop(self.bus))
        for widget in (
            QtWidgets.QLabel("Expression"), self.expression_box,
            QtWidgets.QLabel("State"), self.state_box,
            self.play_button, self.stop_button,
        ):
            controls.addWidget(widget)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.details = QtWidgets.QLabel()
        self.details.setObjectName("Dim")
        self.details.setWordWrap(True)
        layout.addWidget(self.details)

        self.bus.subscribe(_FRAME, self._on_frame)
        self.bus.subscribe(_STATE, self._on_state)
        self._repaint_timer = QtCore.QTimer(self.widget)
        self._repaint_timer.timeout.connect(self._repaint)
        self._repaint_timer.start(16)

    def set_character(self, character: Any) -> None:
        self.character = character
        self.expression_box.blockSignals(True)
        self.state_box.blockSignals(True)
        self.expression_box.clear()
        self.expression_box.addItems(list(character.expressions))
        self.expression_box.setCurrentText(character.default_expression)
        self.state_box.clear()
        states = list(character.mouth_states)
        if states:
            self.state_box.addItems(states)
            self.state_box.setCurrentText(character.default_mouth or states[0])
            self.state_box.setEnabled(True)
        else:
            self.state_box.addItem("—", "")
            self.state_box.setEnabled(False)
        self.expression_box.blockSignals(False)
        self.state_box.blockSignals(False)
        self.details.setText(
            f"kind: {character.kind}   adapter: {character.adapter}   "
            f"default asset: {character.render['asset']}"
        )
        self.screen.setText("Press Play to verify the engine render")

    def select_and_play(self, expression: str, state: str = "") -> None:
        self.expression_box.setCurrentText(expression)
        if state:
            self.state_box.setCurrentText(state)
        self.play()

    def play_sprite_region(self, path: pathlib.Path, src: list[int]) -> None:
        """Preview the Sprite Editor selection through the real renderer."""
        try:
            animation.play_sprite_region(self.bus, path, src)
            self.details.setText(
                f"Sprite Editor selection: {path.name}   src: {src}")
        except Exception as exc:  # noqa: BLE001
            self.details.setText(str(exc))

    def play_bitmap(self, path: pathlib.Path, fg_rgb: tuple[int, int, int],
                    bg_rgb: tuple[int, int, int]) -> None:
        """Preview Bitmap Editor changes through the real adapter."""
        try:
            animation.play_bitmap(
                self.bus, path, fg_rgb=fg_rgb, bg_rgb=bg_rgb)
            self.details.setText(
                f"Bitmap Editor: {path.name}   FG {fg_rgb}   BG {bg_rgb}")
        except Exception as exc:  # noqa: BLE001
            self.details.setText(str(exc))

    def play(self) -> None:
        if self.character is None:
            return
        state = self.state_box.currentData()
        if state is None:
            state = self.state_box.currentText() if self.state_box.isEnabled() else ""
        try:
            animation.play(
                self.bus, self.character, self.expression_box.currentText(), str(state))
        except Exception as exc:  # noqa: BLE001
            self.details.setText(str(exc))

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

    def _repaint(self) -> None:
        if self._status_text:
            self.details.setText(self._status_text)
            self._status_text = None
        if self._frame is None or self.character is None:
            return
        transform = (
            self._QtCore.Qt.FastTransformation
            if animation.scaling(self.character) == "nearest"
            else self._QtCore.Qt.SmoothTransformation
        )
        self.screen.setPixmap(self._QtGui.QPixmap.fromImage(self._frame).scaled(
            self.screen.size(), self._QtCore.Qt.KeepAspectRatio, transform))

    def close(self) -> None:
        try:
            self._repaint_timer.stop()
            self.bus.unsubscribe(_FRAME, self._on_frame)
            self.bus.unsubscribe(_STATE, self._on_state)
        except Exception:  # noqa: BLE001
            pass


class CharacterEditorTab:
    """Select a pack, edit its manifest, and route to its asset editor."""

    def __init__(self, app: Any, qt: tuple, initial_name: str = "",
                 on_character_changed: Any = None) -> None:
        QtCore, _QtGui, QtWidgets = qt
        self._QtCore, self._QtWidgets = QtCore, QtWidgets
        self.project_root = pathlib.Path(__file__).resolve().parent.parent
        self.character = None
        self.manifest_path: pathlib.Path | None = None
        self._loading_text = False
        self._dirty = False
        self._restoring_picker = False
        self._on_character_changed = on_character_changed

        self.preview = CharacterPreviewPane(app, qt)
        self.sprite_editor = SpriteEditorTab(
            app, qt, on_preview=self.preview.play_sprite_region)
        self.bitmap_editor = BitmapEditorTab(
            app, qt, on_preview=self.preview.play_bitmap)
        self.mapping_editor = AssetMappingPane(qt, self.preview.select_and_play)

        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.widget)
        root.setContentsMargins(8, 8, 8, 8)

        header = QtWidgets.QHBoxLayout()
        header.addWidget(QtWidgets.QLabel("Character"))
        self.pack_box = QtWidgets.QComboBox()
        self.pack_box.setMinimumWidth(260)
        header.addWidget(self.pack_box)
        self.kind_label = QtWidgets.QLabel()
        self.kind_label.setObjectName("Dim")
        header.addWidget(self.kind_label)
        header.addStretch(1)
        # Selecting a pack picks the editor that fits it, but every editor
        # stays reachable — Mochi 3.0's were separate launchable scripts, and
        # "open the bitmap editor while a gif pack is loaded" has to keep
        # working or the tool is only half migrated.
        header.addWidget(QtWidgets.QLabel("Editor"))
        self.editor_box = QtWidgets.QComboBox()
        self.editor_box.addItems(["Sprite Editor", "Bitmap Editor", "Asset Map"])
        self.editor_box.currentIndexChanged.connect(self._editor_picked)
        header.addWidget(self.editor_box)
        reload_button = QtWidgets.QPushButton("Reload")
        reload_button.clicked.connect(self.reload)
        header.addWidget(reload_button)
        root.addLayout(header)

        self.pages = QtWidgets.QTabWidget()
        self.pages.addTab(self._build_config_page(), "Config")
        self.editor_stack = QtWidgets.QStackedWidget()
        self.editor_stack.addWidget(self.sprite_editor.widget)
        self.editor_stack.addWidget(self.bitmap_editor.widget)
        self.editor_stack.addWidget(self.mapping_editor.widget)
        self.pages.addTab(self.editor_stack, "Asset Editor")
        self.pages.addTab(self.preview.widget, "Render Preview")
        root.addWidget(self.pages, 1)

        self.pack_box.currentIndexChanged.connect(self._on_pack_picked)
        self._populate_picker(initial_name)

    def _build_config_page(self):
        QtCore, QtWidgets = self._QtCore, self._QtWidgets
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        self.path_label = QtWidgets.QLabel()
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.path_label.setObjectName("Dim")
        layout.addWidget(self.path_label)
        self.config_editor = QtWidgets.QPlainTextEdit()
        self.config_editor.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.config_editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.config_editor, 1)
        footer = QtWidgets.QHBoxLayout()
        self.config_status = QtWidgets.QLabel()
        self.config_status.setObjectName("Dim")
        footer.addWidget(self.config_status, 1)
        save = QtWidgets.QPushButton("Save and validate")
        save.clicked.connect(self.save)
        footer.addWidget(save)
        layout.addLayout(footer)
        return page

    def _populate_picker(self, preferred: str = "") -> None:
        self.pack_box.blockSignals(True)
        self.pack_box.clear()
        selected = 0
        for index, name in enumerate(animation.available()):
            character = animation.load(name)
            display = character.display_name or name
            self.pack_box.addItem(f"{display}  [{name}]", name)
            if name == preferred:
                selected = index
        self.pack_box.setCurrentIndex(selected)
        self.pack_box.blockSignals(False)
        if self.pack_box.count():
            self.select_character(str(self.pack_box.currentData()))

    def _on_pack_picked(self, index: int) -> None:
        if index < 0 or self._restoring_picker:
            return
        previous = self.character.name if self.character else ""
        if not self._resolve_dirty():
            self._restoring_picker = True
            old_index = self.pack_box.findData(previous)
            self.pack_box.setCurrentIndex(old_index)
            self._restoring_picker = False
            return
        self.select_character(str(self.pack_box.itemData(index)))

    def select_character(self, name: str) -> None:
        try:
            character = animation.load(name)
        except Exception as exc:  # noqa: BLE001
            self.config_status.setText(str(exc))
            return
        self.character = character
        self.manifest_path = character.root / "character.yaml"
        self._loading_text = True
        self.config_editor.setPlainText(
            self.manifest_path.read_text(encoding="utf-8"))
        self._loading_text = False
        self._dirty = False
        self.path_label.setText(str(self.manifest_path))
        self.config_status.setText("Loaded and valid")
        self.kind_label.setText(
            f"{character.kind.replace('_', ' ')}  •  {character.adapter}")
        self.preview.set_character(character)
        self.mapping_editor.set_character(character)
        if character.kind == "sprite_sheet":
            self.show_editor(0)
            self.sprite_editor.load_character(character)
        elif character.adapter == "bitmap":
            self.show_editor(1)
            self.bitmap_editor.load_character(character)
        else:
            self.show_editor(2)
        if self._on_character_changed is not None:
            self._on_character_changed(character)

    def show_editor(self, index: int) -> None:
        """Point the Asset Editor page at one of the three editors."""
        self.editor_box.blockSignals(True)
        self.editor_box.setCurrentIndex(index)
        self.editor_box.blockSignals(False)
        self.editor_stack.setCurrentIndex(index)
        self.pages.setTabText(1, self.editor_box.itemText(index))

    def _editor_picked(self, index: int) -> None:
        self.show_editor(index)
        self.pages.setCurrentIndex(1)

    def _on_text_changed(self) -> None:
        if self._loading_text:
            return
        self._dirty = True
        self.config_status.setText("Unsaved changes")

    def _resolve_dirty(self) -> bool:
        if not self._dirty:
            return True
        choice = self._QtWidgets.QMessageBox.question(
            self.widget, "Unsaved character config",
            "Save changes before switching characters?",
            self._QtWidgets.QMessageBox.Save
            | self._QtWidgets.QMessageBox.Discard
            | self._QtWidgets.QMessageBox.Cancel,
            self._QtWidgets.QMessageBox.Save,
        )
        if choice == self._QtWidgets.QMessageBox.Cancel:
            return False
        if choice == self._QtWidgets.QMessageBox.Save:
            return self.save()
        return True

    def save(self) -> bool:
        if self.manifest_path is None or self.character is None:
            return False
        old_text = self.manifest_path.read_text(encoding="utf-8")
        new_text = self.config_editor.toPlainText()
        if new_text and not new_text.endswith("\n"):
            new_text += "\n"
        try:
            self.manifest_path.write_text(new_text, encoding="utf-8")
            loaded = animation.load_path(self.character.root)
        except Exception as exc:  # noqa: BLE001
            self.manifest_path.write_text(old_text, encoding="utf-8")
            self.config_status.setText(f"Not saved: {exc}")
            self._QtWidgets.QMessageBox.critical(
                self.widget, "Invalid character config",
                f"The manifest was not changed.\n\n{exc}")
            return False

        self.character = loaded
        self._loading_text = True
        self.config_editor.setPlainText(new_text)
        self._loading_text = False
        self._dirty = False
        self.config_status.setText("Saved and validated")
        self.kind_label.setText(
            f"{loaded.kind.replace('_', ' ')}  •  {loaded.adapter}")
        self.preview.set_character(loaded)
        self.mapping_editor.set_character(loaded)
        if loaded.kind == "sprite_sheet":
            self.editor_stack.setCurrentWidget(self.sprite_editor.widget)
            self.sprite_editor.load_character(loaded)
            self.pages.setTabText(1, "Sprite Editor")
        elif loaded.adapter == "bitmap":
            self.editor_stack.setCurrentWidget(self.bitmap_editor.widget)
            self.bitmap_editor.load_character(loaded)
            self.pages.setTabText(1, "Bitmap Editor")
        else:
            self.editor_stack.setCurrentWidget(self.mapping_editor.widget)
            self.pages.setTabText(1, f"{loaded.adapter.title()} Editor")
        return True

    def reload(self) -> None:
        if self.character is not None:
            self.select_character(self.character.name)

    def close(self) -> None:
        self.preview.close()
        self.sprite_editor.close()
        self.bitmap_editor.close()


__all__ = ["CharacterEditorTab", "character_asset_rows"]
