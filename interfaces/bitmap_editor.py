"""Packed 1-bit character bitmap editor and engine preview."""

from __future__ import annotations

import json
import pathlib
from typing import Any


def unpack_bitmap(payload: dict[str, Any]) -> tuple[int, int, list[list[bool]]]:
    """Decode Adafruit-GFX-style MSB-first rows without engine code."""
    width = max(1, int(payload.get("width", 0)))
    height = max(1, int(payload.get("height", 0)))
    data = [int(value) & 0xFF for value in payload.get("data", [])]
    stride = (width + 7) // 8
    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            index = y * stride + x // 8
            value = data[index] if index < len(data) else 0
            row.append(bool(value & (1 << (7 - x % 8))))
        pixels.append(row)
    return width, height, pixels


def pack_bitmap(pixels: list[list[bool]]) -> dict[str, Any]:
    """Encode a rectangular bool grid as MSB-first, row-padded bytes."""
    height = len(pixels)
    width = len(pixels[0]) if height else 0
    if width <= 0 or any(len(row) != width for row in pixels):
        raise ValueError("bitmap pixels must be a non-empty rectangular grid")
    stride = (width + 7) // 8
    data = [0] * (stride * height)
    for y, row in enumerate(pixels):
        for x, enabled in enumerate(row):
            if enabled:
                data[y * stride + x // 8] |= 1 << (7 - x % 8)
    return {"width": width, "height": height, "data": data}


class BitmapEditorTab:
    """Edit bitmap character assets and preview through JaegerAnimation."""

    def __init__(self, app: Any, qt: tuple, on_preview: Any = None) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui, self._QtWidgets = QtCore, QtGui, QtWidgets
        self._on_preview = on_preview
        self.character = None
        self.path: pathlib.Path | None = None
        self.pixels: list[list[bool]] = []
        self.fg_rgb = (255, 255, 255)
        self.bg_rgb = (0, 0, 0)

        self.widget = QtWidgets.QWidget()
        root = QtWidgets.QVBoxLayout(self.widget)
        root.setContentsMargins(8, 8, 8, 8)

        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(QtWidgets.QLabel("Bitmap"))
        self.asset_box = QtWidgets.QComboBox()
        self.asset_box.setMinimumWidth(260)
        self.asset_box.currentIndexChanged.connect(self._asset_picked)
        bar.addWidget(self.asset_box)
        self.fg_button = QtWidgets.QPushButton("Foreground")
        self.bg_button = QtWidgets.QPushButton("Background")
        self.fg_button.clicked.connect(lambda: self._choose_color(True))
        self.bg_button.clicked.connect(lambda: self._choose_color(False))
        bar.addWidget(self.fg_button)
        bar.addWidget(self.bg_button)
        open_button = QtWidgets.QPushButton("Open…")
        open_button.clicked.connect(self.open_bitmap)
        bar.addWidget(open_button)
        bar.addStretch(1)
        save = QtWidgets.QPushButton("Save bitmap")
        save.clicked.connect(self.save)
        preview = QtWidgets.QPushButton("Preview in engine")
        preview.clicked.connect(self.preview)
        bar.addWidget(save)
        bar.addWidget(preview)
        root.addLayout(bar)

        self.grid = QtWidgets.QTableWidget()
        # Cocoa accessibility asks every table for cell (0, 0), including a
        # hidden editor that is not applicable to the selected character. A
        # genuine 0x0 model makes Qt repeatedly repair its native table model
        # and log an out-of-bounds warning. Keep one inert cell until a bitmap
        # supplies the real dimensions.
        self.grid.setRowCount(1)
        self.grid.setColumnCount(1)
        self.grid.setItem(0, 0, QtWidgets.QTableWidgetItem())
        self.grid.setEnabled(False)
        self.grid.setAccessibleName("Bitmap pixel editor")
        self.grid.setShowGrid(True)
        self.grid.horizontalHeader().hide()
        self.grid.verticalHeader().hide()
        self.grid.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.grid.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.grid.cellClicked.connect(self._toggle)
        root.addWidget(self.grid, 1)

        self.status = QtWidgets.QLabel(
            "Select a Bitmap Man face; click cells to toggle its packed bits.")
        self.status.setStyleSheet("color:#777784;")
        root.addWidget(self.status)
        self._refresh_color_buttons()

    def load_character(self, character: Any) -> bool:
        if character.adapter != "bitmap":
            return False
        self.character = character
        paths: list[pathlib.Path] = []
        for spec in character.expressions.values():
            asset = spec.get("clips") or spec.get("asset") or character.render["asset"]
            if isinstance(asset, str):
                path = character.root / asset
                if path.suffix.lower() == ".json" and path not in paths:
                    paths.append(path)
        self.asset_box.blockSignals(True)
        self.asset_box.clear()
        for path in paths:
            self.asset_box.addItem(path.stem.replace("_", " ").title(), str(path))
        self.asset_box.blockSignals(False)
        if paths:
            self.asset_box.setCurrentIndex(0)
            return self.load_path(paths[0])
        self.status.setText("This bitmap character declares no JSON faces.")
        return False

    def open_bitmap(self) -> None:
        """Edit any packed bitmap, not only the selected pack's faces.

        Mochi 3.0's editors were standalone scripts you pointed at a file.
        Keeping that entry point means the editor stays reachable when the
        chosen character is a gif or a video, which is what the character
        combo alone cannot do.
        """
        root = pathlib.Path(__file__).resolve().parent.parent
        start = (self.character.root if self.character is not None
                 else root / "assets" / "bitmaps")
        path, _ = self._QtWidgets.QFileDialog.getOpenFileName(
            self.widget, "Open packed bitmap", str(start),
            "Bitmap JSON (*.json);;All files (*)")
        if path:
            self.load_path(pathlib.Path(path))

    def _asset_picked(self, index: int) -> None:
        if index >= 0:
            self.load_path(pathlib.Path(str(self.asset_box.itemData(index))))

    def load_path(self, path: pathlib.Path) -> bool:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            width, height, pixels = unpack_bitmap(payload)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Could not load {path}: {exc}")
            return False
        self.path, self.pixels = path, pixels
        self.grid.setEnabled(True)
        self.grid.clearContents()
        self.grid.setRowCount(height)
        self.grid.setColumnCount(width)
        cell = max(7, min(18, 760 // max(width, height)))
        for x in range(width):
            self.grid.setColumnWidth(x, cell)
        for y in range(height):
            self.grid.setRowHeight(y, cell)
            for x in range(width):
                item = self._QtWidgets.QTableWidgetItem()
                self.grid.setItem(y, x, item)
                self._paint(item, pixels[y][x])
        self.status.setText(f"{path} — {width} × {height}, MSB-first")
        self.preview()
        return True

    def _toggle(self, row: int, column: int) -> None:
        self.pixels[row][column] = not self.pixels[row][column]
        self._paint(self.grid.item(row, column), self.pixels[row][column])
        self.status.setText("Unsaved bitmap changes")

    def _paint(self, item: Any, enabled: bool) -> None:
        rgb = self.fg_rgb if enabled else self.bg_rgb
        item.setBackground(self._QtGui.QColor(*rgb))

    def _choose_color(self, foreground: bool) -> None:
        current = self.fg_rgb if foreground else self.bg_rgb
        color = self._QtWidgets.QColorDialog.getColor(
            self._QtGui.QColor(*current), self.widget)
        if not color.isValid():
            return
        value = (color.red(), color.green(), color.blue())
        if foreground:
            self.fg_rgb = value
        else:
            self.bg_rgb = value
        self._refresh_color_buttons()
        for y, row in enumerate(self.pixels):
            for x, enabled in enumerate(row):
                self._paint(self.grid.item(y, x), enabled)
        self.preview()

    def _refresh_color_buttons(self) -> None:
        self.fg_button.setStyleSheet(
            f"background:rgb{self.fg_rgb}; color:#000;")
        self.bg_button.setStyleSheet(
            f"background:rgb{self.bg_rgb}; color:#fff;")

    def preview(self) -> None:
        if self.path is not None and self._on_preview is not None:
            self._on_preview(self.path, self.fg_rgb, self.bg_rgb)

    def save(self) -> bool:
        if self.path is None:
            return False
        try:
            content = json.dumps(pack_bitmap(self.pixels), indent=2) + "\n"
            self.path.write_text(content, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Save failed: {exc}")
            return False
        self.status.setText(f"Saved {self.path}")
        self.preview()
        return True

    def close(self) -> None:
        pass


__all__ = ["BitmapEditorTab", "pack_bitmap", "unpack_bitmap"]
