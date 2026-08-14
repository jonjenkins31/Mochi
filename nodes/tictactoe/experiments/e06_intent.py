"""E06 — intent. A character that chooses how hard to play.

    python -m nodes.tictactoe.experiments.e06_intent

Absolute knowledge of the rules; personality about how to use it. The
same player, three intents:

    win    take the best value available
    even   play properly, do not run away with it
    let    concede — leave them a way back

THE DETAIL THAT MAKES IT WORK: a softened move is CHOSEN BY VALUE, from
the ranked search, not randomised. A random bad move reads as a bug. The
second-best move reads as someone going easy on you, which is the thing
you actually want when playing with a child — and it is only possible
because search already computed what every square is worth.
"""

from __future__ import annotations

from .. import HybridPlayer, NeuralPlayer, RandomPlayer, duel, game
from . import header, table


def main() -> int:
    header("E06 · intent",
           "Can it play hard, then let a kid win — without looking broken?")

    net = NeuralPlayer(hidden=32).train(positions=100_000, rate=0.03)
    kid = RandomPlayer(seed=3)
    rows = []
    for intent in HybridPlayer.INTENTS:
        player = HybridPlayer(policy=net, intent=intent)
        tally = duel(player, kid, games=60, seed=4)
        rows.append((intent, tally["hybrid"], tally["draw"], tally["random"]))
    table(rows, ("intent", "it wins", "draws", "THEY win"))

    print("\n  Same weights, same rules, same opponent. Only the intent")
    print("  changed — and the opponent goes from never winning to winning")
    print("  most of the time.\n")

    board = game.place(game.place(game.new_board(), 4, "X"), 0, "O")
    print("  On one position, what each intent picks and what it is worth:")
    valued = dict(game.rank(board, "X"))
    for intent in HybridPlayer.INTENTS:
        square = HybridPlayer(policy=net, intent=intent).move(board, "X")
        print(f"    {intent:5} -> square {square}  (value {valued[square]:+d})")
    print("\n  Every one of those is a legal, understood move. Conceding")
    print("  picks a worse VALUE, not a random square — that is the")
    print("  difference between going easy and being broken.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
