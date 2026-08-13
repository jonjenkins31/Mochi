"""Skinnable, frameless popup player migrated from Mochi 3.0/v4.

Unlike the archived ZMQ player, this window subscribes to JaegerOS's current
display-frame topic. Skins remain ordinary assets: one YAML file points at a
bezel image and declares the rectangle where rendered frames belong.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import pathlib
from typing import Any, Callable

import yaml
from PySide6 import QtCore, QtGui, QtWidgets

from jaeger_os import topics


@dataclass(frozen=True)
class PlayerSkin:
    id: str
    name: str
    image: pathlib.Path
    screen_bbox: tuple[int, int, int, int]
    description: str = ""


@dataclass(frozen=True)
class PlayerSettings:
    skin: str = "tv1"
    canvas: tuple[int, int] = (512, 512)
    scale: float = 0.75
    opacity: float = 1.0
    topmost: bool = True
    draggable: bool = True
    framing: str = "fill"
    pixel_art: bool = True


def _pair(value: Any, default: tuple[int, int]) -> tuple[int, int]:
    try:
        if len(value) == 2:
            return max(64, int(value[0])), max(64, int(value[1]))
    except (TypeError, ValueError):
        pass
    return default


def load_player_settings(root: pathlib.Path) -> PlayerSettings:
    path = root / "assets" / "player_settings.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    return PlayerSettings(
        skin=str(data.get("skin", "tv1")),
        canvas=_pair(data.get("canvas"), (512, 512)),
        scale=max(0.1, min(4.0, float(data.get("scale", 0.75)))),
        opacity=max(0.1, min(1.0, float(data.get("opacity", 1.0)))),
        topmost=bool(data.get("topmost", True)),
        draggable=bool(data.get("draggable", True)),
        framing=str(data.get("framing", "fill")),
        pixel_art=bool(data.get("pixel_art", True)),
    )


def save_player_settings(root: pathlib.Path, settings: PlayerSettings) -> None:
    path = root / "assets" / "player_settings.yaml"
    data = {
        "schema": "mochi/popup-player/v1",
        "skin": settings.skin,
        "canvas": list(settings.canvas),
        "scale": settings.scale,
        "opacity": settings.opacity,
        "topmost": settings.topmost,
        "draggable": settings.draggable,
        "framing": settings.framing,
        "pixel_art": settings.pixel_art,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def discover_skins(root: pathlib.Path) -> dict[str, PlayerSkin]:
    skins: dict[str, PlayerSkin] = {}
    for manifest in sorted((root / "assets" / "skins").glob("*/skin.yaml")):
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            bbox = tuple(int(v) for v in data["screen_bbox"])
            image = root / str(data["image"])
            skin = PlayerSkin(
                id=str(data.get("id") or manifest.parent.name),
                name=str(data.get("name") or manifest.parent.name),
                image=image.resolve(),
                screen_bbox=bbox,  # type: ignore[arg-type]
                description=str(data.get("description", "")),
            )
            if len(bbox) == 4 and image.is_file():
                skins[skin.id] = skin
        except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError):
            continue
    return skins


class PopupPlayerWindow(QtWidgets.QWidget):
    """A draggable desktop character window driven only by bus frames."""

    def __init__(
        self,
        bus: Any,
        root: pathlib.Path,
        settings: PlayerSettings,
        *,
        on_settings: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.bus = bus
        self.root = root
        self.settings = settings
        self.skins = discover_skins(root)
        self._on_settings = on_settings
        self._drag_offset: QtCore.QPoint | None = None
        self._pending: QtGui.QImage | None = None
        self._last: QtGui.QImage | None = None
        self._destroying = False

        self.setWindowTitle("Mochi Popup Player")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.screen = QtWidgets.QLabel(self)
        self.screen.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.screen.setStyleSheet("background:#000; border:0;")
        self.screen.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.body = QtWidgets.QLabel(self)
        self.body.setStyleSheet("background:transparent; border:0;")
        self.body.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.apply_settings(settings)
        self.bus.subscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._paint_pending)
        self._timer.start(16)

    def apply_settings(self, settings: PlayerSettings) -> None:
        self.settings = settings
        flags = (QtCore.Qt.WindowType.Window
                 | QtCore.Qt.WindowType.FramelessWindowHint)
        if settings.topmost:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        visible = self.isVisible()
        self.setWindowFlags(flags)
        self.setWindowOpacity(settings.opacity)

        skin = self.skins.get(settings.skin)
        if skin is None:
            width = max(64, int(settings.canvas[0] * settings.scale))
            height = max(64, int(settings.canvas[1] * settings.scale))
            self.resize(width, height)
            self.body.hide()
            self.screen.setGeometry(0, 0, width, height)
        else:
            pixmap = QtGui.QPixmap(str(skin.image))
            width = max(1, int(pixmap.width() * settings.scale))
            height = max(1, int(pixmap.height() * settings.scale))
            pixmap = pixmap.scaled(
                width, height,
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation)
            self.resize(width, height)
            self.body.setGeometry(0, 0, width, height)
            self.body.setPixmap(pixmap)
            self.body.show()
            left, top, sw, sh = skin.screen_bbox
            self.screen.setGeometry(
                int(left * settings.scale), int(top * settings.scale),
                max(1, int(sw * settings.scale)),
                max(1, int(sh * settings.scale)))
            self.body.raise_()
        if self._last is not None:
            self._show_image(self._last)
        if visible:
            self.show()

    def show_player(self) -> None:
        if self.pos().isNull():
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is not None:
                self.move(screen.availableGeometry().center()
                          - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_frame(self, msg: Any) -> None:
        if not getattr(msg, "data", None):
            return
        width, height = int(msg.width), int(msg.height)
        if width <= 0 or height <= 0:
            return
        image = QtGui.QImage(
            bytes(msg.data), width, height, width * 4,
            QtGui.QImage.Format.Format_RGBA8888)
        self._pending = image.copy()

    def _paint_pending(self) -> None:
        if self._pending is not None:
            self._last, self._pending = self._pending, None
            self._show_image(self._last)

    def _show_image(self, image: QtGui.QImage) -> None:
        mode = (QtCore.Qt.AspectRatioMode.IgnoreAspectRatio
                if self.settings.framing == "fill"
                else QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        transform = (QtCore.Qt.TransformationMode.FastTransformation
                     if self.settings.pixel_art
                     else QtCore.Qt.TransformationMode.SmoothTransformation)
        self.screen.setPixmap(QtGui.QPixmap.fromImage(image).scaled(
            self.screen.size(), mode, transform))

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.settings.draggable:
                self._drag_offset = (event.globalPosition().toPoint()
                                     - self.frameGeometry().topLeft())
        elif event.button() == QtCore.Qt.MouseButton.RightButton:
            menu = QtWidgets.QMenu(self)
            settings_action = menu.addAction("Player settings…")
            hide_action = menu.addAction("Hide player")
            picked = menu.exec(event.globalPosition().toPoint())
            if picked is settings_action and self._on_settings:
                self._on_settings()
            elif picked is hide_action:
                self.hide()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        if event.key() in (QtCore.Qt.Key.Key_Escape, QtCore.Qt.Key.Key_Q):
            self.hide()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if not self._destroying:
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)

    def shutdown(self) -> None:
        self._destroying = True
        self._timer.stop()
        try:
            self.bus.unsubscribe(topics.ACT_DISPLAY_FRAME, self._on_frame)
        except Exception:  # noqa: BLE001
            pass
        self.close()


class PopupPlayerSettingsDialog(QtWidgets.QDialog):
    """All legacy popup-player settings, kept separate for consolidation."""

    def __init__(self, controller: "PopupPlayerController", parent: Any = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle("Popup Player Settings")
        self.setMinimumWidth(470)
        outer = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.skin = QtWidgets.QComboBox()
        self.skin.addItem("No skin (plain canvas)", "")
        for skin in controller.player.skins.values():
            self.skin.addItem(skin.name, skin.id)
        form.addRow("Skin", self.skin)

        canvas = QtWidgets.QHBoxLayout()
        self.width = QtWidgets.QSpinBox(); self.width.setRange(64, 4096)
        self.height = QtWidgets.QSpinBox(); self.height.setRange(64, 4096)
        canvas.addWidget(self.width); canvas.addWidget(QtWidgets.QLabel("×"))
        canvas.addWidget(self.height)
        form.addRow("Plain canvas", canvas)

        self.scale = QtWidgets.QDoubleSpinBox()
        self.scale.setRange(0.1, 4.0); self.scale.setSingleStep(0.05)
        form.addRow("Scale", self.scale)
        self.opacity = QtWidgets.QDoubleSpinBox()
        self.opacity.setRange(0.1, 1.0); self.opacity.setSingleStep(0.05)
        form.addRow("Opacity", self.opacity)
        self.framing = QtWidgets.QComboBox(); self.framing.addItems(["fill", "contain"])
        form.addRow("Frame fit", self.framing)
        self.topmost = QtWidgets.QCheckBox("Stay above other windows")
        form.addRow("", self.topmost)
        self.draggable = QtWidgets.QCheckBox("Drag anywhere to move")
        form.addRow("", self.draggable)
        self.pixel_art = QtWidgets.QCheckBox("Nearest-neighbor frame scaling")
        form.addRow("", self.pixel_art)
        outer.addLayout(form)

        self.preview = QtWidgets.QLabel("No skin")
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(150)
        self.preview.setStyleSheet("background:#08080b; border:1px solid #33333f;")
        outer.addWidget(self.preview)

        buttons = QtWidgets.QDialogButtonBox()
        open_player = buttons.addButton(
            "Open Player", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)
        apply_button = buttons.addButton(
            "Apply", QtWidgets.QDialogButtonBox.ButtonRole.ApplyRole)
        save_button = buttons.addButton(
            "Save", QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        close_button = buttons.addButton(QtWidgets.QDialogButtonBox.StandardButton.Close)
        open_player.clicked.connect(controller.show)
        apply_button.clicked.connect(self.apply)
        save_button.clicked.connect(self.save)
        close_button.clicked.connect(self.close)
        outer.addWidget(buttons)
        self.skin.currentIndexChanged.connect(self._update_preview)
        self.load()

    def load(self) -> None:
        s = self.controller.settings
        index = self.skin.findData(s.skin)
        self.skin.setCurrentIndex(max(0, index))
        self.width.setValue(s.canvas[0]); self.height.setValue(s.canvas[1])
        self.scale.setValue(s.scale); self.opacity.setValue(s.opacity)
        self.framing.setCurrentText(s.framing)
        self.topmost.setChecked(s.topmost); self.draggable.setChecked(s.draggable)
        self.pixel_art.setChecked(s.pixel_art)
        self._update_preview()

    def values(self) -> PlayerSettings:
        return PlayerSettings(
            skin=str(self.skin.currentData() or ""),
            canvas=(self.width.value(), self.height.value()),
            scale=self.scale.value(), opacity=self.opacity.value(),
            topmost=self.topmost.isChecked(),
            draggable=self.draggable.isChecked(),
            framing=self.framing.currentText(),
            pixel_art=self.pixel_art.isChecked())

    def apply(self) -> None:
        self.controller.apply(self.values(), persist=False)

    def save(self) -> None:
        self.controller.apply(self.values(), persist=True)

    def _update_preview(self) -> None:
        skin = self.controller.player.skins.get(str(self.skin.currentData() or ""))
        if skin is None:
            self.preview.setPixmap(QtGui.QPixmap())
            self.preview.setText("Plain frameless canvas")
            return
        self.preview.setText("")
        self.preview.setPixmap(QtGui.QPixmap(str(skin.image)).scaled(
            430, 170, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation))


class PopupPlayerController:
    """Own the popup, settings dialog, bus subscription, and teardown."""

    def __init__(self, app: Any) -> None:
        self.root = pathlib.Path(getattr(app, "root", pathlib.Path.cwd())).resolve()
        self.settings = load_player_settings(self.root)
        self.dialog: PopupPlayerSettingsDialog | None = None
        self.player = PopupPlayerWindow(
            app.bus, self.root, self.settings, on_settings=self.open_settings)

    def show(self) -> None:
        self.player.show_player()

    def open_settings(self, parent: Any = None) -> None:
        if self.dialog is None:
            self.dialog = PopupPlayerSettingsDialog(self, parent)
        self.dialog.load()
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def apply(self, settings: PlayerSettings, *, persist: bool) -> None:
        self.settings = replace(settings)
        self.player.apply_settings(self.settings)
        if persist:
            save_player_settings(self.root, self.settings)

    def close(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
        self.player.shutdown()


__all__ = [
    "PlayerSkin", "PlayerSettings", "discover_skins", "load_player_settings",
    "save_player_settings", "PopupPlayerWindow", "PopupPlayerSettingsDialog",
    "PopupPlayerController",
]
