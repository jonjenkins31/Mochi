"""E03 — a net that imitates. How much training buys how much skill?

    python -m nodes.tictactoe.experiments.e03_neural

An 18-24-9 MLP in pure Python, trained on positions labelled by
exhaustive search. The point is the CURVE, not the final number: the
first few thousand samples buy most of the skill and the rest gets
expensive, which is the shape everyone eventually meets.

It also produces the failure the next episode fixes — a net that agrees
with perfect play most of the time and still loses games, because a
policy is a preference and a preference is sometimes wrong.
"""

from __future__ import annotations

from .. import (HeuristicPlayer, MinimaxPlayer, NeuralPlayer, RandomPlayer,
                agreement, duel)
from . import header, table, timed


def main() -> int:
    header("E03 · learning by imitation",
           "How much training does the last few percent cost?")

    rows, previous = [], 0.0
    for count, rate in ((1_000, 0.05), (10_000, 0.05),
                        (100_000, 0.03), (300_000, 0.02)):
        net, elapsed = timed(
            lambda c=count, r=rate: NeuralPlayer(hidden=32).train(positions=c, rate=r))
        score = agreement(net)
        rows.append((f"{count:,}", f"{elapsed:.1f}s", f"{score:.0%}",
                     f"+{score - previous:.0%}"))
        previous = score
    table(rows, ("positions", "time", "agrees with best", "gained"))

    print("\n  Diminishing, and it never reaches 100%. The last few percent")
    print("  is the expensive part of machine learning — and it is exactly")
    print("  what E04 gets for free.\n")

    net = NeuralPlayer(hidden=32).train(positions=300_000, rate=0.02)
    rivals = (RandomPlayer(seed=1), HeuristicPlayer(), MinimaxPlayer())
    rows = [(rival.name,
             (t := duel(net, rival, games=40, seed=4))[net.name],
             t["draw"], t[rival.name]) for rival in rivals]
    table(rows, ("against", "won", "drew", "LOST"))
    print("\n  It agrees with perfect play most of the time and still loses")
    print("  to RANDOM. That is the gap a rule closes on the first sample.\n")

    net.save("nodes/tictactoe/policy.json")
    print("  saved -> nodes/tictactoe/policy.json\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
