"""Standalone media popup retained from Mochi v4."""

from __future__ import annotations

import pathlib
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

_IMAGES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
_VIDEOS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


class MediaView(QtWidgets.QWidget):
    """Play an image, GIF, or video using Qt's native media surfaces."""

    def __init__(self) -> None:
        super().__init__()
        self._path = pathlib.Path()
        self._kind = ""
        self._movie: QtGui.QMovie | None = None
        self._player: Any = None
        self._audio: Any = None
        self._video: QtWidgets.QWidget | None = None
        self._pixmap: QtGui.QPixmap | None = None
        self._stack = QtWidgets.QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self.label = QtWidgets.QLabel("Pick an image, GIF, or video")
        self.label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(240, 180)
        self._stack.addWidget(self.label)

    def play(self, path: pathlib.Path) -> None:
        self.stop()
        self._path = pathlib.Path(path)
        if not self._path.is_file():
            self.label.setText(f"Not found:\n{self._path}")
            return
        suffix = self._path.suffix.lower()
        if suffix in _VIDEOS:
            self._kind = "video"; self._play_video()
        elif suffix == ".gif":
            self._kind = "gif"
            self._movie = QtGui.QMovie(str(self._path))
            self.label.setMovie(self._movie); self._movie.start()
            self._stack.setCurrentWidget(self.label)
        else:
            self._kind = "image"
            self._pixmap = QtGui.QPixmap(str(self._path))
            self._rescale(); self._stack.setCurrentWidget(self.label)

    def _play_video(self) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget
        except ImportError:
            self.label.setText("Qt Multimedia is unavailable")
            self._stack.setCurrentWidget(self.label)
            return
        if self._video is None:
            self._video = QVideoWidget(); self._stack.addWidget(self._video)
        self._player = QMediaPlayer(); self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)
        self._player.setSource(QtCore.QUrl.fromLocalFile(str(self._path)))
        self._stack.setCurrentWidget(self._video); self._player.play()

    def _rescale(self) -> None:
        if self._pixmap is not None and not self._pixmap.isNull():
            self.label.setPixmap(self._pixmap.scaled(
                self.label.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation))

    def stop(self) -> None:
        if self._movie is not None:
            self._movie.stop(); self.label.setMovie(None); self._movie = None
        if self._player is not None:
            self._player.stop(); self._player = None; self._audio = None

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._kind == "image":
            self._rescale()


class FloatingMediaPlayer(QtWidgets.QWidget):
    """The old frameless media window, with file controls restored."""

    def __init__(self, root: pathlib.Path) -> None:
        super().__init__()
        self.root = root
        self.setWindowTitle("Mochi Media Player")
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.resize(520, 430)
        self.setStyleSheet(
            "QWidget{background:#0e0c16;color:#d5d2e4;}"
            "QPushButton{background:#29243b;border:1px solid #413b57;"
            "border-radius:5px;padding:5px 9px;}")
        outer = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        open_button = QtWidgets.QPushButton("Open…")
        open_button.clicked.connect(self.open_file)
        controls.addWidget(open_button)
        controls.addStretch(1)
        hide_button = QtWidgets.QPushButton("×")
        hide_button.clicked.connect(self.hide)
        controls.addWidget(hide_button)
        outer.addLayout(controls)
        self.view = MediaView(); outer.addWidget(self.view, 1)
        self._drag: QtCore.QPoint | None = None

    def open_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open media", str(self.root / "assets"),
            "Media (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.mov *.mkv *.webm);;All files (*)")
        if path:
            self.view.play(pathlib.Path(path))

    def show_player(self, path: pathlib.Path | None = None) -> None:
        if path is not None:
            self.view.play(path)
        self.show(); self.raise_(); self.activateWindow()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        self._drag = None

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        event.ignore(); self.hide()

    def shutdown(self) -> None:
        self.view.stop(); self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        super().close()


__all__ = ["MediaView", "FloatingMediaPlayer"]

