"""Tic-tac-toe as a panel pane — the second thing the side panel holds.

The panel exists to be DYNAMIC: chat is one way to interact with the
character, a game is another, and there will be more. One pane is a
splitter; two is a contract. This is the second one, and it is what the
contract turned out to be:

    .widget   the thing to put in the panel
    .close()  drop timers and subscriptions
    TITLE     what the selector calls it

`ChatTab` already satisfied that without being changed, which is the
only reason it counts as a contract rather than a wish.

The character reacts here exactly as it does on the Stage tab, because
it is the same two calls: `animation.play()` for the face and
`mind.ask()` for the line. The face is immediate and the words catch up
— a reaction that waits for inference is not a reaction.

The Stage tab has its own copy of this board, still, deliberately: that
one is an operator's test rig with the strategy pickers wired to a
research node, and this one is something a person plays. Merging them
means the operator's version dictates the player's, and that trade is
not obviously worth it yet.
"""

from __future__ import annotations

from typing import Any

from modules import jaeger_agent as mind
from modules import jaeger_animation as animation
from nodes import tictactoe


class GamePane:
    """A game of tic-tac-toe against the character."""

    TITLE = "tic-tac-toe"

    def __init__(self, app: Any, qt: tuple, character_of: Any = None) -> None:
        QtCore, _QtGui, QtWidgets = qt
        self._QtCore = QtCore
        self.bus = app.bus
        self.character_of = character_of
        self.game: Any = None
        self._match: Any = None

        self.widget = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(self.widget)
        column.setContentsMargins(10, 10, 10, 10)
        column.setSpacing(8)

        controls = QtWidgets.QHBoxLayout()
        self.intent = QtWidgets.QComboBox()
        self.intent.addItems(list(tictactoe.HybridPlayer.INTENTS))
        self.intent.setToolTip(
            "how hard it plays. `let` means it can decide to lose to you — "
            "the rules stay exact either way.")
        controls.addWidget(QtWidgets.QLabel("plays to"))
        controls.addWidget(self.intent, 1)
        start = QtWidgets.QPushButton("New game")
        start.clicked.connect(self.start)
        controls.addWidget(start)
        column.addLayout(controls)

        board = QtWidgets.QGridLayout()
        board.setSpacing(4)
        self.squares = []
        for index in range(9):
            cell = QtWidgets.QPushButton(" ")
            cell.setFixedSize(58, 58)
            cell.setStyleSheet("font-size:24px;font-weight:600;")
            cell.setEnabled(False)
            cell.clicked.connect(lambda _c=False, n=index: self.play(n))
            self.squares.append(cell)
            board.addWidget(cell, index // 3, index % 3)
        holder = QtWidgets.QHBoxLayout()
        holder.addStretch(1)
        holder.addLayout(board)
        holder.addStretch(1)
        column.addLayout(holder)

        self.status = QtWidgets.QLabel("press New game.")
        self.status.setStyleSheet("color:#777784;")
        self.status.setWordWrap(True)
        column.addWidget(self.status)
        column.addStretch(1)

    # ── the game ─────────────────────────────────────────────────

    def start(self) -> None:
        """Always the hybrid player: it has the rules exactly and the
        intent decides what it does with them. Which strategy is a
        research question and it lives on the Stage tab, not here."""
        self.game = tictactoe.Session(
            strategy="hybrid", intent=self.intent.currentText())
        self.status.setText("your move — you are O.")
        self._refresh()
        self._agent_move()

    def play(self, square: int) -> None:
        if self.game is None or self.game.over:
            return
        if self.game.human_turn(square) is None:
            return
        self._refresh()
        if self.game.over:
            self._react()
        else:
            self._agent_move()

    def _agent_move(self) -> None:
        move = self.game.agent_turn()
        if move is None:
            return
        self._refresh()
        self._react(move)

    def _react(self, move: Any = None) -> None:
        state = move.state if move else self.game.situation()
        face = move.face if move else tictactoe.FACE_FOR.get(state, "neutral")
        character = self.character_of() if self.character_of else None
        if character is not None:
            try:
                animation.play(self.bus, character, face)
            except Exception:  # noqa: BLE001 — a face is never worth raising
                pass
        try:
            mind.ask(self.bus, (
                f"You are playing tic-tac-toe with someone. The game is: "
                f"{state}. Say ONE short line about it, in character."),
                session="mochi-1")
        except Exception:  # noqa: BLE001
            pass

    def _refresh(self) -> None:
        board = self.game.board if self.game else " " * 9
        playable = self.game is not None and not self.game.over
        for index, cell in enumerate(self.squares):
            cell.setText(board[index] if board[index] != " " else " ")
            cell.setEnabled(playable and board[index] == " ")
        if self.game is not None and self.game.over:
            self.status.setText({
                "agent": "it wins.", "human": "you win.",
                "draw": "a draw.",
            }.get(self.game.result, "over."))

    def close(self) -> None:
        if self._match is not None:
            self._match.stop()
            self._match = None


__all__ = ["GamePane"]
