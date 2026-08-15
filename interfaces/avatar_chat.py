"""Character on the left, the conversation on the right — one window.

JaegerAI's avatar+chat surface, rebuilt out of parts Mochi already has:
[`CharacterView`](character_view.py) beside a real
[`ChatTab`](chat.py). Nothing here is a new chat client. That matters,
because the JaegerAI original had to draw its own mic and speaker
buttons and could only WRITE A CONFIG FILE with them — its comment says
so: "the live mic can't flip mid-session today". Mochi's switches start
and stop the nodes, so reusing the tab is both the shorter path and the
one where the buttons work.

The conversation is shared, not copied: the tab in the window and the
tab in the main window subscribe to the same topics, so both show the
same turns and either can send.
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .character_view import CharacterView
from .chat import ChatTab


class AvatarChatWindow(QtWidgets.QWidget):
    """The companion surface: watch the character while you talk to it."""

    def __init__(self, app: Any, *, character_of: Any = None) -> None:
        super().__init__()
        self.setWindowTitle("Mochi — character + chat")
        self.setObjectName("AvatarChat")
        self.setStyleSheet(
            "QWidget#AvatarChat{background:#0B0910;}"
            "QFrame#Stage{background:#141021;border:1px solid #2A2340;"
            "border-radius:12px;}"
            "QLabel#StageHeader{font-family:Menlo,monospace;font-size:10px;"
            "color:#777784;}")
        self.resize(1240, 700)

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(14, 14, 14, 14)
        row.setSpacing(12)

        stage = QtWidgets.QFrame()
        stage.setObjectName("Stage")
        column = QtWidgets.QVBoxLayout(stage)
        column.setContentsMargins(14, 12, 14, 14)
        column.setSpacing(8)
        header = QtWidgets.QLabel("CHARACTER")
        header.setObjectName("StageHeader")
        column.addWidget(header)
        self.view = CharacterView(app, character_of=character_of)
        column.addWidget(self.view, 1)
        row.addWidget(stage, 4)

        # A whole tab, as a pane. Its mic and speaker switches, its
        # pipeline picker and its self-speech gate all come along.
        self.chat = ChatTab(app, (QtCore, QtGui, QtWidgets))
        # The tab's header — state, pipeline picker, two switches, New
        # conversation — is a single row that clips rather than wraps.
        # Below this it lies about what is available.
        self.chat.widget.setMinimumWidth(660)
        row.addWidget(self.chat.widget, 5)

    def show_window(self) -> None:
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def shutdown(self) -> None:
        self.chat.close()
        self.view.shutdown()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        super().close()


__all__ = ["AvatarChatWindow"]
