"""The agent's window: the character, and a panel you pull out to interact.

This is the primary surface. The tabbed window is the OPERATOR's — every
setting, switch and editor lives there — and this one is what the
character is. A person talking to Mochi should need nothing else on
screen.

    ┌──────────────┬─────────────────┐
    │              │  chat │ game    │   ← panel: hidden until wanted
    │  character   │                 │
    │              │  the interactive│
    │          [›] │  zone           │
    └──────────────┴─────────────────┘

THE PANEL IS THE POINT. It is not "the chat pane" — chat is one pane in
it. A game is another. Anything the character can do WITH you belongs
here, selected from the strip along the top, so adding an interaction
never means adding a window.

A pane is any object with three things, which is small enough that
`ChatTab` already satisfied it unchanged:

    .widget   what goes in the panel
    .close()  drop timers and subscriptions
    TITLE     what the selector calls it

Panes are built on FIRST SELECTION. A pane that has never been shown
should not be subscribing to a bus or training a policy, and one of
these does both.

NOTHING HERE COMES FROM JAEGERAI. The idea of an avatar beside a
conversation is common to both projects; this is Mochi's parts —
`CharacterView`, `ChatTab`, `nodes/tictactoe` — in a splitter.
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .character_view import CharacterView

#: Panel width when it opens, and the width it returns to after being
#: collapsed. Wide enough for the chat header, which clips rather than
#: wraps and below this lies about which switches are available.
PANEL_W = 660

#: Icon colours: lit when the switch is on, dim when it is off.
ON, OFF = "#43E08A", "#7C8A81"


def _icon(kind: str, colour: str, *, crossed: bool) -> QtGui.QIcon:
    """A mic or a speaker, drawn rather than shipped.

    Twenty lines of QPainter instead of an SVG file and a QtSvg import,
    and the slash for OFF is the same stroke on either glyph — which is
    the whole reason both states read as one control.
    """
    pixmap = QtGui.QPixmap(22, 22)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(colour), 1.7)
    pen.setCapStyle(QtCore.Qt.RoundCap)
    pen.setJoinStyle(QtCore.Qt.RoundJoin)
    painter.setPen(pen)
    if kind == "mic":
        painter.drawRoundedRect(QtCore.QRectF(8, 2, 6, 11), 3, 3)
        painter.drawArc(QtCore.QRectF(4.5, 5, 13, 12), 180 * 16, 180 * 16)
        painter.drawLine(11, 17, 11, 20)
    else:
        path = QtGui.QPainterPath()
        path.moveTo(10, 5); path.lineTo(6, 8.5); path.lineTo(3, 8.5)
        path.lineTo(3, 14); path.lineTo(6, 14); path.lineTo(10, 17.5)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawArc(QtCore.QRectF(11, 7.5, 5, 7), -80 * 16, 160 * 16)
        painter.drawArc(QtCore.QRectF(13, 4.5, 7, 13), -80 * 16, 160 * 16)
    if crossed:
        painter.drawLine(3, 3, 19, 19)
    painter.end()
    return QtGui.QIcon(pixmap)


def _panes() -> dict[str, Any]:
    """name -> factory(app, qt, character_of).

    Both take the same three arguments, which is what a registry is
    for. Imported here and not at module scope: a pane that fails to
    import should break that pane, not the window.
    """
    from .chat import ChatTab
    from .game_pane import GamePane

    return {
        "chat": ChatTab,
        "game": GamePane,
    }


class AvatarWindow(QtWidgets.QWidget):
    """The character, with an interactive panel that slides out beside it."""

    def __init__(self, app: Any, *, character_of: Any = None,
                 windows: Any = ()) -> None:
        """`windows` is (label, shortcut, callback) per File-menu entry.

        Passed in rather than looked up: this window is the front door
        and must not import the operator window to name it, or the
        primary surface depends on the secondary one.
        """
        super().__init__()
        self.app = app
        self.character_of = character_of
        self._built: dict[str, Any] = {}
        #: Width with the panel shut, so closing it gives that back.
        self._narrow = 0
        self._classes = _panes()

        self.setWindowTitle("Mochi")
        self.setObjectName("AvatarWindow")
        self.setStyleSheet(
            "QWidget#AvatarWindow{background:#0B0910;}"
            "QFrame#Stage{background:#141021;border:1px solid #2A2340;"
            "border-radius:12px;}"
            "QWidget#Panel{background:#141021;border:1px solid #2A2340;"
            "border-radius:12px;}"
            "QLabel#StageHeader{font-family:Menlo,monospace;font-size:10px;"
            "color:#777784;}"
            "QPushButton#Tab{background:transparent;border:none;padding:6px 14px;"
            "color:#8A85A6;font-size:12px;}"
            "QPushButton#Tab:checked{color:#e8e6f0;border-bottom:2px solid #6C5CE7;}"
            "QPushButton#Handle{background:rgba(255,255,255,0.06);border:none;"
            "border-radius:14px;color:#8A85A6;font-size:15px;}"
            "QPushButton#Switch{background:rgba(255,255,255,0.05);border:none;"
            "border-radius:19px;}"
            "QPushButton#Switch:checked{background:rgba(67,224,138,0.18);}"
            "QPushButton#Switch:disabled{background:rgba(255,255,255,0.02);}")
        self.resize(520, 620)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setMenuBar(self._menus(windows))
        self.body = body = QtWidgets.QWidget()
        outer = QtWidgets.QHBoxLayout(body)
        outer.setContentsMargins(14, 14, 14, 14)
        root.addWidget(body, 1)
        self.split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.split.setHandleWidth(12)
        self.split.setChildrenCollapsible(False)
        outer.addWidget(self.split)

        self.split.addWidget(self._stage(app, character_of))
        self.panel = self._panel()
        self.panel.setVisible(False)          # hidden until wanted
        self.split.addWidget(self.panel)
        self.split.setStretchFactor(0, 4)
        self.split.setStretchFactor(1, 5)

    def _menus(self, windows: Any) -> QtWidgets.QMenuBar:
        """File → every other window. On macOS this lands in the system
        menu bar, which is where someone looks for it."""
        # Both held on self. A QMenu whose only reference is a local
        # gets collected, and the menu bar is left with an entry that
        # opens a deleted object.
        self.menubar = bar = QtWidgets.QMenuBar(self)
        self.file_menu = menu = bar.addMenu("File")
        for label, shortcut, callback in windows:
            if label == "-":
                menu.addSeparator()
                continue
            action = menu.addAction(label)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(callback)
        menu.addSeparator()
        quit_ = menu.addAction("Quit Mochi")
        quit_.setShortcut("Ctrl+Q")
        quit_.setMenuRole(QtGui.QAction.QuitRole)
        quit_.triggered.connect(QtWidgets.QApplication.quit)
        return bar

    # ── the two halves ───────────────────────────────────────────

    def _stage(self, app: Any, character_of: Any) -> QtWidgets.QFrame:
        stage = QtWidgets.QFrame()
        stage.setObjectName("Stage")
        stage.setMinimumWidth(280)
        column = QtWidgets.QVBoxLayout(stage)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel("CHARACTER")
        label.setObjectName("StageHeader")
        header.addWidget(label)
        header.addStretch(1)
        column.addLayout(header)

        self.view = CharacterView(app, character_of=character_of)
        column.addWidget(self.view, 1)

        # Ears and voice, under the character — the reference design put
        # them here and it is right: they are things the CHARACTER does,
        # not settings of a chat pane, and they have to be reachable
        # with the panel shut.
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        self.mic_btn = self._switch("mic", "listen")
        self.speaker_btn = self._switch("speaker", "speak replies")
        # Grey them at BUILD time, not after the first click. A switch
        # with no module installed or no node declared cannot move, and
        # finding that out by pressing it is finding out too late.
        # Reading `available()` is not owning the switch — the chat tab
        # reads the same answer.
        from core import audio_switch
        can_hear, can_speak = audio_switch.available(app)
        for button, allowed in ((self.mic_btn, can_hear),
                                (self.speaker_btn, can_speak)):
            button.setEnabled(allowed)
            if not allowed:
                button.setToolTip(f"{button.toolTip().split(' —')[0]} — "
                                  "not available in this manifest")
        footer.addWidget(self.mic_btn)
        footer.addWidget(self.speaker_btn)
        footer.addStretch(1)
        self.handle = QtWidgets.QPushButton("›")
        self.handle.setObjectName("Handle")
        self.handle.setFixedSize(28, 28)
        self.handle.setToolTip("open the interactive panel")
        self.handle.clicked.connect(lambda: self.toggle_panel())
        footer.addWidget(self.handle)
        column.addLayout(footer)
        return stage

    def _switch(self, kind: str, what: str) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton()
        button.setObjectName("Switch")
        button.setCheckable(True)
        button.setFixedSize(38, 38)
        button.setIconSize(QtCore.QSize(22, 22))
        button.setCursor(QtCore.Qt.PointingHandCursor)
        button.setToolTip(f"{what} — off")
        button.setIcon(_icon(kind, OFF, crossed=True))
        button.clicked.connect(lambda on, k=kind: self._audio_clicked(k, on))
        return button

    def _audio_clicked(self, kind: str, on: bool) -> None:
        """Drive the CHAT TAB's switch, never the audio node directly.

        That tab already knows the whole story — that ticking Listen has
        to start the ears if they are off, that a reply spoken aloud has
        to deafen the microphone so the character does not answer
        itself. A second control that skips all of it would be a second
        control that gets it wrong, so this one is a remote for the
        first. It is also why using a switch builds the chat pane: the
        thing that owns the switch has to exist to be told.
        """
        chat = self._built.get("chat") or self.show_pane("chat")
        (chat.mic if kind == "mic" else chat.speak).setChecked(on)

    def _follow_audio(self, chat: Any) -> None:
        """Both views of one fact. The tab's checkbox is the fact — it
        can refuse a switch that has no module or no node behind it —
        so the round button follows it rather than the click."""
        chat.mic.toggled.connect(
            lambda on: self._paint_switch(self.mic_btn, "mic", "listen", on))
        chat.speak.toggled.connect(
            lambda on: self._paint_switch(
                self.speaker_btn, "speaker", "speak replies", on))
        for button, kind, what, box in (
                (self.mic_btn, "mic", "listen", chat.mic),
                (self.speaker_btn, "speaker", "speak replies", chat.speak)):
            button.setEnabled(box.isEnabled())
            if not box.isEnabled():
                button.setToolTip(box.toolTip())
            self._paint_switch(button, kind, what, box.isChecked())

    def _paint_switch(self, button: Any, kind: str, what: str,
                      on: bool) -> None:
        button.setChecked(on)
        button.setIcon(_icon(kind, ON if on else OFF, crossed=not on))
        button.setToolTip(f"{what} — {'on' if on else 'off'}")

    def _panel(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        panel.setObjectName("Panel")
        panel.setMinimumWidth(PANEL_W)
        column = QtWidgets.QVBoxLayout(panel)
        column.setContentsMargins(10, 6, 10, 10)
        column.setSpacing(0)

        strip = QtWidgets.QHBoxLayout()
        strip.setSpacing(2)
        self.tabs = QtWidgets.QButtonGroup(self)
        self.tabs.setExclusive(True)
        for index, name in enumerate(self._classes):
            button = QtWidgets.QPushButton(name)
            button.setObjectName("Tab")
            button.setCheckable(True)
            button.setCursor(QtCore.Qt.PointingHandCursor)
            self.tabs.addButton(button, index)
            strip.addWidget(button)
        strip.addStretch(1)
        self.tabs.idClicked.connect(
            lambda index: self.show_pane(list(self._classes)[index]))
        column.addLayout(strip)

        self.stack = QtWidgets.QStackedWidget()
        column.addWidget(self.stack, 1)
        return panel

    # ── the panel ────────────────────────────────────────────────

    def toggle_panel(self, *, open_: bool | None = None) -> None:
        """Slide the panel in or out, growing the WINDOW to make room.

        Without the resize the panel opens by squeezing the character
        down to nothing, which reads as the window breaking rather than
        a panel appearing. Closing restores the width the window had
        before it opened — remembered rather than recomputed, because
        the splitter has been dragged since and its arithmetic no longer
        describes what the person actually wants back.
        """
        wanted = (not self.panel.isVisible()) if open_ is None else open_
        if wanted == self.panel.isVisible():
            return
        if wanted and not self._built:
            self.show_pane(next(iter(self._classes)))
        self.handle.setText("\u2039" if wanted else "\u203a")
        self.handle.setToolTip(
            "hide the interactive panel" if wanted
            else "open the interactive panel")
        if wanted:
            self._narrow = self.width()
            stage_w = self.split.sizes()[0] or self._narrow
            self.panel.setVisible(True)
            self.resize(self._narrow + PANEL_W + self.split.handleWidth(),
                        self.height())
            self.split.setSizes([stage_w, PANEL_W])
        else:
            self.panel.setVisible(False)
            # The window cannot shrink below a minimum that still counts
            # the panel. Hiding a widget only invalidates that on the
            # next layout pass, and the resize happens before it. Both
            # layouts: the splitter is in the body, the body is in the
            # window, and only the outer one clamps resize().
            self.body.layout().activate()
            self.layout().activate()
            if self._narrow:
                self.resize(self._narrow, self.height())

    def show_pane(self, name: str) -> Any:
        """Select a pane, building it the first time it is asked for."""
        pane = self._built.get(name)
        if pane is None:
            pane = self._classes[name](
                self.app, (QtCore, QtGui, QtWidgets), self.character_of)
            self._built[name] = pane
            self.stack.addWidget(pane.widget)
            if name == "chat":
                self._follow_audio(pane)
        self.stack.setCurrentWidget(pane.widget)
        button = self.tabs.button(list(self._classes).index(name))
        if button is not None:
            button.setChecked(True)
        return pane

    # ── lifecycle ────────────────────────────────────────────────

    def show_window(self) -> None:
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        """Closing the front door closes the app. Every other window
        here hides and is reopened from the File menu; this one has no
        menu to be reopened from."""
        event.accept()
        QtWidgets.QApplication.quit()

    def shutdown(self) -> None:
        for pane in self._built.values():
            try:
                pane.close()
            except Exception:  # noqa: BLE001
                pass
        self.view.shutdown()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        super().close()


__all__ = ["AvatarWindow", "PANEL_W"]
