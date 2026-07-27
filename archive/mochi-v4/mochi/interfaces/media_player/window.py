"""Media player widgets: :class:`MediaView` (embeddable) +
:class:`FloatingMediaPlayer` (frameless floating window)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QImage, QMovie, QPixmap
from PySide6.QtWidgets import QLabel, QStackedLayout, QVBoxLayout, QWidget

_IMAGE = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_GIF = {".gif"}
_VIDEO = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def media_kind(path: str) -> str:
    """image | gif | video — by extension (best-effort image fallback)."""
    ext = Path(path).suffix.lower()
    if ext in _GIF:
        return "gif"
    if ext in _VIDEO:
        return "video"
    return "image"


class MediaView(QWidget):
    """Chrome-less surface that plays one image / gif / video file.

    Embeddable (the Studio Media tab drops it inline) and reusable inside the
    floating window. Native Qt rendering — no custom decoders.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MediaView")
        self._path = ""
        self._kind = ""
        self._movie: QMovie | None = None
        self._player: Any = None
        self._audio: Any = None
        self._video: QWidget | None = None

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("Drop a file or pick one to play")
        self._label.setObjectName("MediaLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(200, 150)
        self._stack.addWidget(self._label)

    # ── playback ──────────────────────────────────────────────────
    def play(self, path: str) -> None:
        self.stop()
        path = str(path)
        self._path, self._kind = path, media_kind(path)
        if not Path(path).exists():
            self._label.setMovie(None)
            self._label.setText(f"not found:\n{Path(path).name}")
            self._stack.setCurrentWidget(self._label)
            return
        if self._kind == "video":
            self._play_video(path)
        elif self._kind == "gif":
            self._movie = QMovie(path)
            self._label.setMovie(self._movie)
            self._movie.start()
            self._stack.setCurrentWidget(self._label)
        else:
            self._show_image(path)

    def _show_image(self, path: str) -> None:
        self._pixmap = QPixmap(path)
        self._rescale_image()
        self._stack.setCurrentWidget(self._label)

    def _rescale_image(self) -> None:
        pm = getattr(self, "_pixmap", None)
        if pm and not pm.isNull():
            self._label.setPixmap(pm.scaled(
                self._label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def _play_video(self, path: str) -> None:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        if self._video is None:
            self._video = QVideoWidget()
            self._stack.addWidget(self._video)
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._stack.setCurrentWidget(self._video)
        self._player.play()

    def stop(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self._label.setMovie(None)
            self._movie = None
        if self._player is not None:
            self._player.stop()
            self._player = None
            self._audio = None

    def feed_frame(self, data: bytes, w: int, h: int) -> None:
        """Render one RGBA frame streamed from the media node."""
        img = QImage(bytes(data), w, h, w * 4, QImage.Format.Format_RGBA8888)
        self._label.setPixmap(QPixmap.fromImage(img).scaled(
            self._label.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self._stack.setCurrentWidget(self._label)

    def current(self) -> str:
        return self._path

    def resizeEvent(self, e: Any) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(e)
        if self._kind == "image":
            self._rescale_image()


class FloatingMediaPlayer(QWidget):
    """Frameless, draggable, always-on-top media window (mochi-v4 style)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Mochi Media")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(380, 320)
        self.setStyleSheet(
            "QWidget{background:#0E0C16;border-radius:14px;}"
            "QLabel#MediaLabel{color:#8A85A6;font-size:13px;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        self.view = MediaView()
        lay.addWidget(self.view)
        self._drag: Any = None

    def play(self, path: str) -> None:
        self.view.play(path)
        self.show()
        self.raise_()
        self.activateWindow()

    # ── drag + dismiss ────────────────────────────────────────────
    def mousePressEvent(self, e: Any) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e: Any) -> None:  # noqa: N802
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e: Any) -> None:  # noqa: N802
        self._drag = None

    def keyPressEvent(self, e: Any) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.view.stop()
            self.hide()


def make_surface(ctx: Any, spec: Any = None) -> FloatingMediaPlayer:  # noqa: ARG001
    """Chassis surface — the only bus coupling. Subscribes to the media
    node's state and plays whatever it reports. No core changes."""
    win = FloatingMediaPlayer()
    bus = getattr(ctx, "bus", None)
    if bus is not None:
        from mochi.app.surfaces import make_bus_bridge
        from mochi.transport import topics
        win._bridge = make_bus_bridge(
            bus, [topics.SENSE_MEDIA_FRAME, topics.SENSE_MEDIA_STATE])

        def _on_msg(msg: Any) -> None:
            t = getattr(msg, "topic", "")
            if t == topics.SENSE_MEDIA_FRAME:
                win.view.feed_frame(msg.data, msg.width, msg.height)
                if not win.isVisible():
                    win.show(); win.raise_()
        win._bridge.message.connect(_on_msg)
    return win
