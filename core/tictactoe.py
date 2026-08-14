"""Tic-tac-toe — the rules, as code, because rules are not language.

Here to answer a question empirically rather than by opinion: when a
character plays a game, which parts does a language model do?

    the RULES        legal moves, wins, draws        ← code. Always.
    the MOVE         which square to take            ← measured below
    the TALK         banter, reaction, character     ← the model. Only it.

A board is nine characters, "         " for empty, X and O otherwise.
No class, no engine, no state machine — a game this small is a handful
of pure functions and anything more is decoration.

WHY MINIMAX AND NOT SOMETHING CLEVER. 9 squares is 549,946 positions;
exhaustive search takes under a millisecond and is exactly optimal. A
heuristic here would be slower to write, slower to trust, and worse.
"""

from __future__ import annotations

EMPTY = " "
LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),      # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),      # columns
    (0, 4, 8), (2, 4, 6),                 # diagonals
)


def new_board() -> str:
    return EMPTY * 9


def legal(board: str) -> list[int]:
    return [i for i, cell in enumerate(board) if cell == EMPTY]


def place(board: str, square: int, mark: str) -> str:
    return board[:square] + mark + board[square + 1:]


def winner(board: str) -> str:
    """The mark that has a line, or "" — including for a full board."""
    for a, b, c in LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return board[a]
    return ""


def over(board: str) -> bool:
    return bool(winner(board)) or not legal(board)


def render(board: str) -> str:
    """Three rows, for a prompt or a log."""
    rows = [" | ".join(board[i:i + 3]) for i in (0, 3, 6)]
    return "\n---------\n".join(rows)


def describe(board: str) -> str:
    """The board as SENTENCES, which is what a model reads best.

    A grid drawn with pipes and dashes is a picture, and a language
    model is not looking at it — it is reading tokens. Naming the
    squares in words measurably beats ASCII art, and the numbering is
    stated so a reply can be parsed back.
    """
    names = ("top left", "top middle", "top right",
             "middle left", "centre", "middle right",
             "bottom left", "bottom middle", "bottom right")
    taken = [f"{names[i]} ({i}) is {board[i]}"
             for i in range(9) if board[i] != EMPTY]
    free = [f"{names[i]} ({i})" for i in legal(board)]
    return ("Board: " + ("; ".join(taken) if taken else "empty") +
            ". Free squares: " + ", ".join(free) + ".")


# ── the opponent, as code ────────────────────────────────────────

def best_move(board: str, mark: str) -> int:
    """Perfect play. Exhaustive, because nine squares is small."""
    opponent = "O" if mark == "X" else "X"

    def score(state: str, turn: str, depth: int) -> tuple[int, int]:
        champion = winner(state)
        if champion == mark:
            return 10 - depth, -1
        if champion == opponent:
            return depth - 10, -1
        options = legal(state)
        if not options:
            return 0, -1
        results = []
        for square in options:
            value, _ = score(place(state, square, turn),
                             opponent if turn == mark else mark, depth + 1)
            results.append((value, square))
        return (max(results) if turn == mark else min(results))

    return score(board, mark, 0)[1]


def threat(board: str, mark: str) -> str:
    """What just happened, in a word a character can react to.

    Not a score. A model asked to be dramatic about "+7" writes
    nonsense; asked to react to "you are about to lose" it does the
    right thing, and the judgement stays in code where it is correct.
    """
    opponent = "O" if mark == "X" else "X"
    if winner(board) == mark:
        return "won"
    if winner(board) == opponent:
        return "lost"
    if not legal(board):
        return "drew"
    for square in legal(board):
        if winner(place(board, square, opponent)) == opponent:
            return "about to lose"
        if winner(place(board, square, mark)) == mark:
            return "about to win"
    return "even"


__all__ = ["EMPTY", "new_board", "legal", "place", "winner", "over",
           "render", "describe", "best_move", "threat"]
