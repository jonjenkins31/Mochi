"""One game, turn by turn — the surface any agent plays through.

Either seat takes a strategy or a person, so the same object covers a
character playing you, two strategies playing each other, and anything
with a `.move()` joining in from outside this package.

`players.py` answers "which square"; this answers "whose turn, what just
happened, and what should the character do about it". It is the whole
difference between a strategy and something a character can PLAY.

Deliberately knows nothing about characters, buses, faces or models. It
takes a strategy and returns facts:

    session = Session(strategy="hybrid", intent="win")
    move = session.agent_turn()        # -> Move(square, state, ...)
    session.human_turn(4)

So any agent can partake: give it a strategy and a way to speak, and the
turn-taking is the same whether the mover is minimax, a net, or a
language model. The character layer decides what a face and a voice do
with `move.state`; this decides nothing about presentation.

WHY `state` IS A WORD. It comes back as "about to lose", not a score.
A model asked to be dramatic about "-7" writes nonsense; asked to react
to "about to lose" it writes something a character would say. The
judgement stays in code, where it is exact, and only the wording is
delegated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import game
from .players import HybridPlayer, NeuralPlayer

#: What the character's face should do about each outcome, before it has
#: said anything. A reaction is fast and inference is not, so the face
#: comes from the same word the model gets and never waits for it.
FACE_FOR = {
    "won": "happy", "lost": "sad", "drew": "neutral",
    "about to win": "happy", "about to lose": "look_down", "even": "neutral",
}


@dataclass
class Move:
    """One turn, and everything a character needs to react to it."""

    square: int
    mark: str
    board: str
    state: str                  # a WORD: won / about to lose / even / …
    face: str                   # the expression that word implies
    over: bool
    result: str                 # "" until the game ends: agent / human / draw
    by: str = ""                # which strategy chose it


class Session:
    """A single game. Each seat is a strategy, or a person."""

    def __init__(self, strategy: Any = "hybrid", *, agent_mark: str = "X",
                 intent: str = "win", trained: int = 100_000,
                 opponent: Any = None) -> None:
        """`strategy` takes one seat; `opponent` takes the other.

        `opponent=None` means a person sits there — the common case, and
        the reason this is not symmetrical in its defaults. Naming a
        second strategy makes it agent-versus-agent, and nothing else
        changes: the same Move objects come back, so a character reacts
        to a machine opponent exactly as it reacts to a person.

        Either seat accepts a NAME or an already-built player, which is
        how a language model or anything else with `.move()` joins in
        without this file knowing it exists.
        """
        self.agent_mark = agent_mark
        self.human_mark = "O" if agent_mark == "X" else "X"
        self.player = self._seat(strategy, intent, trained)
        #: The other seat. None means a person plays it.
        self.opponent = self._seat(opponent, "win", trained) if opponent else None
        self.board = game.new_board()
        self.moves: list[Move] = []

    def _seat(self, who: Any, intent: str, trained: int) -> Any:
        from . import STRATEGIES

        if who is None or not isinstance(who, str):
            return who                             # already built, or nobody
        if who == "hybrid":
            return HybridPlayer(
                policy=NeuralPlayer(hidden=32).train(positions=trained),
                intent=intent)
        return STRATEGIES[who]()

    def player_for(self, mark: str) -> Any:
        """Whoever holds that seat, or None when a person does."""
        return self.player if mark == self.agent_mark else self.opponent

    @property
    def autonomous(self) -> bool:
        """True when neither seat needs a person — the match can run
        itself, which is what makes agent-versus-agent a loop rather
        than a UI."""
        return self.opponent is not None

    # ── state ────────────────────────────────────────────────────

    @property
    def over(self) -> bool:
        return game.over(self.board)

    @property
    def result(self) -> str:
        champion = game.winner(self.board)
        if not champion:
            return "draw" if self.over else ""
        return "agent" if champion == self.agent_mark else "human"

    @property
    def turn(self) -> str:
        """Whose move it is, from the board alone — no flag to desync."""
        return "X" if self.board.count("X") <= self.board.count("O") else "O"

    def legal(self) -> list[int]:
        return game.legal(self.board)

    # ── turns ────────────────────────────────────────────────────

    def agent_turn(self) -> Move | None:
        if self.over or self.turn != self.agent_mark:
            return None
        square = self.player.move(self.board, self.agent_mark)
        return self._record(square, self.agent_mark,
                            by=getattr(self.player, "name", "?"))

    def opponent_turn(self) -> Move | None:
        """The other seat's move, when a strategy holds it."""
        if self.over or self.opponent is None or self.turn == self.agent_mark:
            return None
        square = self.opponent.move(self.board, self.human_mark)
        return self._record(square, self.human_mark,
                            by=getattr(self.opponent, "name", "?"))

    def step(self) -> Move | None:
        """Advance whoever is due. None means it is a person's turn.

        One call for both shapes: a UI polls it and gets None when it
        should wait for a click; a match loop calls it until the game
        ends. Neither has to know which seats are filled.
        """
        if self.over:
            return None
        if self.turn == self.agent_mark:
            return self.agent_turn()
        return self.opponent_turn()

    def play_out(self, limit: int = 9) -> list[Move]:
        """Run an autonomous match to the end. Refuses if a seat is
        human — silently skipping a person's turn would be a game they
        never got to play."""
        if not self.autonomous:
            raise ValueError("a seat is human; call step() and human_turn()")
        played = []
        while not self.over and len(played) < limit:
            move = self.step()
            if move is None:
                break
            played.append(move)
        return played

    def human_turn(self, square: int) -> Move | None:
        """A person's move. Illegal squares are refused, not corrected —
        an interface that quietly moves your piece somewhere else is
        worse than one that says no."""
        if self.over or square not in self.legal():
            return None
        if self.opponent is not None and self.turn != self.agent_mark:
            return None          # that seat belongs to a strategy
        return self._record(square, self.human_mark, by="human")

    def _record(self, square: int, mark: str, by: str) -> Move:
        self.board = game.place(self.board, square, mark)
        # The state is always read from the AGENT's point of view, so a
        # character reacting to its opponent's move says the right thing.
        state = game.threat(self.board, self.agent_mark)
        move = Move(square=square, mark=mark, board=self.board, state=state,
                    face=FACE_FOR.get(state, "neutral"), over=self.over,
                    result=self.result, by=by)
        self.moves.append(move)
        return move

    # ── for a character to say something about ───────────────────

    def situation(self) -> str:
        """One sentence a language model can react to, with no board in
        it. Everything decidable has already been decided."""
        if self.over:
            return {"agent": "you won", "human": "you lost",
                    "draw": "it is a draw"}[self.result]
        return game.threat(self.board, self.agent_mark)

    def render(self) -> str:
        return game.render(self.board)


__all__ = ["Session", "Move", "FACE_FOR"]
