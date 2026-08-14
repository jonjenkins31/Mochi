"""E05 — evolution. Learning with no teacher, only a scoreboard.

    python -m nodes.tictactoe.experiments.e05_evolution

Imitation (E03) needs a teacher that already knows the answer. Most
things worth automating have no such teacher — nobody can label the
right servo angle for "look pleased", but anybody can say which of two
attempts looked better. Evolution needs only that.

THE RESULT THAT MATTERS: evolving a bare policy is slow and bad.
Evolving the SAME policy inside the rules is fast and good, at a
fraction of the budget — because no generation is spent rediscovering
legality or immediate tactics. Known facts do not only make the player
safer, they make the SEARCH smaller.
"""

from __future__ import annotations

from .. import HybridPlayer, RandomPlayer, agreement, duel, evolve
from . import header, table, timed


def main() -> int:
    header("E05 · evolution",
           "Can it learn with no teacher — and do known rules help?")

    rows = []
    for population, generations, games in ((20, 40, 10), (30, 100, 12)):
        budget = population * generations * games
        for inside in (False, True):
            net, elapsed = timed(lambda: evolve(
                population=population, generations=generations, games=games,
                seed=2, with_rules=inside))
            player = HybridPlayer(policy=net, intent="win") if inside else net
            tally = duel(player, RandomPlayer(seed=1), games=40, seed=4)
            rows.append((f"{budget:,}", "inside rules" if inside else "bare",
                         f"{elapsed:.1f}s", f"{agreement(player):.0%}",
                         tally["random"]))
    table(rows, ("games played", "search space", "time",
                 "agrees with best", "lost to random"))

    print("\n  Same algorithm, same budget, one difference: whether the")
    print("  candidate plays inside the rules while being scored. The")
    print("  rules are not helping it play — they are shrinking what it")
    print("  has to search, which is why the cheaper run wins.\n")
    print("  No labels were used anywhere in this experiment.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
