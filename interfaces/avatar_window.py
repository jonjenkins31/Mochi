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


def _panes() -> dict[str, Any]:
    """name -> factory(app, qt, character_of).

    Factories rather than classes so a pane that does not care which
    character is loaded — chat does not — simply ignores the argument,
    instead of every pane growing a parameter to satisfy the registry.
    Imported here and not at module scope: a pane that fails to import
    should break that pane, not the window.
    """
    from .chat import ChatTab
    from .game_pane import GamePane

    return {
        "chat": lambda app, qt, _character_of: ChatTab(app, qt),
        "game": GamePane,
    }


class AvatarWindow(QtWidgets.QWidget):
    """The character, with an interactive panel that slides out beside it."""

    def __init__(self, app: Any, *, character_of: Any = None) -> None:
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
            "border-radius:14px;color:#8A85A6;font-size:15px;}")
        self.resize(520, 620)

        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
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

        # The handle sits UNDER the character rather than floating over
        # it. A button on top of a face is a button in the way of the
        # thing the window is for.
        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        self.handle = QtWidgets.QPushButton("›")
        self.handle.setObjectName("Handle")
        self.handle.setFixedSize(28, 28)
        self.handle.setToolTip("open the interactive panel")
        self.handle.clicked.connect(lambda: self.toggle_panel())
        footer.addWidget(self.handle)
        column.addLayout(footer)
        return stage

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
            # next layout pass, and the resize happens before it.
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
        self.stack.setCurrentWidget(pane.widget)
        button = self.tabs.button(list(self._classes).index(name))
        if button is not None:
            button.setChecked(True)
        return pane

    # ── lifecycle ────────────────────────────────────────────────

    def show_window(self) -> None:
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        event.ignore()
        self.hide()

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
