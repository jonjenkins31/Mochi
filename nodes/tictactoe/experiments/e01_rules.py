"""E01 — fixed code. How far do written-down rules get you?

    python -m nodes.tictactoe.experiments.e01_rules

The baseline every later episode is measured against. No learning, no
model: a coin flip, a ladder of if-statements, and exhaustive search.

The result worth noticing is that the LADDER — five lines a person can
read — never loses to anything, while agreeing with perfect play less
than half the time. Tic-tac-toe has many equally-drawing moves, so
"agrees with the optimal move" and "plays well" are different questions,
and most benchmarks quietly measure the first.
"""

from __future__ import annotations

from .. import (HeuristicPlayer, MinimaxPlayer, RandomPlayer, agreement,
                duel, game)
from . import header, table, timed


def main() -> int:
    header("E01 · fixed code",
           "How good can you get without any learning at all?")

    players = [RandomPlayer(seed=1), HeuristicPlayer(), MinimaxPlayer()]
    rows = []
    for player in players:
        (score, elapsed) = timed(lambda p=player: agreement(p, positions=300))
        losses = sum(duel(player, rival, games=60, seed=4)[rival.name]
                     for rival in players if rival.name != player.name)
        rows.append((player.name, player.kind, f"{score:.0%}",
                     f"{losses}/120", f"{elapsed*1000:.0f}ms"))
    table(rows, ("strategy", "kind", "agrees with best",
                 "games lost", "300 moves in"))

    print("\n  The ladder agrees less than half the time and never loses.")
    print("  Agreement with the optimal move is not the same as playing")
    print("  well — a drawn game is a success, and many moves draw.\n")

    board = game.place(game.place(game.new_board(), 0, "X"), 4, "O")
    print("  A position, and what each square is actually worth to X:")
    print("  " + game.render(board).replace("\n", "\n  "))
    print(f"\n  {game.rank(board, 'X')}")
    print("  (square, value) — positive wins, 0 draws, negative loses.")
    print("  Every later episode is trying to approximate this list.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
