"""Assets tab — browse everything playable, and see it played.

The last piece of Mochi 3.0 Studio that had not been carried over. Its
sprite, bitmap, mscript and resource editors all became Qt in v5; the
`AssetPreviewer` — a file tree with thumbnails — did not, which left
"what does this file actually look like?" answerable only by opening it
in something.

THE PREVIEW IS THE REAL RENDERER, and that is the whole point. Studio
was useful because its edit→preview loop went through the shipping
decoders rather than a second implementation that could drift and lie.
This keeps that property by not decoding anything at all: selecting a
file publishes /act/display/play and the frames come back on
/act/display/frame from the engine that will play it for real. A gif, an
mp4, a packed bitmap, a procedural scene and a motion script are all
just a path — the adapter is chosen inside the engine, by extension.

So this tab is a file tree, a publish, and a QLabel. Qt's own
QFileSystemModel does the tree, the watching and the filtering; the
thumbnail cache 3.0 needed is gone because there is nothing to cache
when the renderer is a topic away.
"""

from __future__ import annotations

import pathlib
from typing import Any

from jaeger_os import topics

from modules import jaeger_animation as animation

_FRAME = topics.ACT_DISPLAY_FRAME
_STATE = topics.ACT_DISPLAY_STATE

#: What the engine has an adapter for. Same list the Face tab's file
#: dialog offers, as globs for QFileSystemModel.
PLAYABLE = (
    "*.gif", "*.apng", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp",
    "*.tif", "*.tiff", "*.mp4", "*.mov", "*.mkv", "*.webm", "*.m4v",
    "*.avi", "*.json", "*.mscript", "*.py",
)


class AssetsTab:
    """Walk the project's assets and play whichever one is selected."""

    def __init__(self, app: Any, qt: tuple) -> None:
        QtCore, QtGui, QtWidgets = qt
        self._QtCore, self._QtGui = QtCore, QtGui
        self.bus = app.bus
        self.project_root = pathlib.Path(
            getattr(app, "root", None) or pathlib.Path(__file__).resolve().parent.parent)
        self._frame = None
        self._reason: str | None = None
        self.selected: pathlib.Path | None = None

        self.widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.widget)
        layout.setContentsMargins(8, 8, 8, 8)

        bar = QtWidgets.QHBoxLayout()
        self.auto = QtWidgets.QCheckBox("Play on select")
        self.auto.setChecked(True)
        self.auto.setToolTip(
            "publish /act/display/play as soon as a file is picked. Off: "
            "browse without disturbing whatever is on the face.")
        bar.addWidget(self.auto)
        self.loop = QtWidgets.QCheckBox("Loop")
        self.loop.setChecked(True)
        bar.addWidget(self.loop)
        for label, slot in (("Play", self.play), ("Stop", self.stop)):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(slot)
            bar.addWidget(button)
        bar.addStretch(1)
        self.path_label = QtWidgets.QLabel("nothing selected")
        self.path_label.setStyleSheet("color:#6a6a78;")
        bar.addWidget(self.path_label)
        layout.addLayout(bar)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Qt watches the directory and refreshes itself — an asset
        # dropped in while the app runs shows up without a Refresh button.
        self.model = QtGui.QFileSystemModel() if hasattr(QtGui, "QFileSystemModel") \
            else QtWidgets.QFileSystemModel()
        self.model.setRootPath(str(self.project_root))
        self.model.setNameFilters(list(PLAYABLE))
        # Show non-matching files greyed rather than hidden, so a folder
        # never looks empty when it merely holds something else.
        self.model.setNameFilterDisables(True)
        self.tree = QtWidgets.QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(self.project_root)))
        for column in (1, 2, 3):
            self.tree.hideColumn(column)
        self.tree.setHeaderHidden(True)
        self.tree.selectionModel().currentChanged.connect(self._picked)
        splitter.addWidget(self.tree)

        preview_box = QtWidgets.QGroupBox("Live preview — the engine's own frames")
        preview_layout = QtWidgets.QVBoxLayout(preview_box)
        self.preview = QtWidgets.QLabel("pick a file")
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumSize(280, 280)
        self.preview.setStyleSheet("background:#000; border:1px solid #33333f;")
        preview_layout.addWidget(self.preview, 1)
        self.state = QtWidgets.QLabel()
        self.state.setWordWrap(True)
        self.state.setStyleSheet("color:#777784;")
        preview_layout.addWidget(self.state)
        splitter.addWidget(preview_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)

        self.bus.subscribe(_FRAME, self._on_frame)
        self.bus.subscribe(_STATE, self._on_state)
        self._timer = QtCore.QTimer(self.widget)
        self._timer.timeout.connect(self._repaint)
        self._timer.start(16)

    # ── driving it ───────────────────────────────────────────────

    def _picked(self, current: Any, _previous: Any = None) -> None:
        path = pathlib.Path(self.model.filePath(current))
        if not path.is_file():
            return
        self.selected = path
        try:
            shown = path.relative_to(self.project_root)
        except ValueError:
            shown = path
        self.path_label.setText(str(shown))
        if self.auto.isChecked():
            self.play()

    def play(self) -> None:
        """One publish. The engine picks the decoder by extension, which
        is why this file knows about no format at all."""
        if self.selected is None:
            return
        animation.play_file(self.bus, self.selected, loop=self.loop.isChecked())

    def stop(self) -> None:
        animation.stop(self.bus)

    # ── bus thread: record only ──────────────────────────────────

    def _on_frame(self, msg: Any) -> None:
        if not msg.data or msg.width <= 0 or msg.height <= 0:
            return
        image = self._QtGui.QImage(
            bytes(msg.data), msg.width, msg.height, msg.width * 4,
            self._QtGui.QImage.Format_RGBA8888)
        self._frame = image.copy()

    def _on_state(self, msg: Any) -> None:
        reason = str(getattr(msg, "reason", "") or "")
        if reason:
            self._reason = reason

    # ── GUI thread ───────────────────────────────────────────────

    def _repaint(self) -> None:
        if self._reason is not None:
            self.state.setText(self._reason)
            self._reason = None
        frame, self._frame = self._frame, None
        if frame is None:
            return
        self.preview.setPixmap(self._QtGui.QPixmap.fromImage(frame).scaled(
            self.preview.size(), self._QtCore.Qt.KeepAspectRatio,
            self._QtCore.Qt.FastTransformation))

    def close(self) -> None:
        self._timer.stop()
        for topic, handler in ((_FRAME, self._on_frame), (_STATE, self._on_state)):
            try:
                self.bus.unsubscribe(topic, handler)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["AssetsTab", "PLAYABLE"]
