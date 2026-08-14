"""E04 — rules over a policy. Buying the last few percent for nothing.

    python -m nodes.tictactoe.experiments.e04_hybrid

The architecture this whole series is arguing toward: a learned
preference, vetoed by constraints that cannot be wrong.

    rules      remove provably bad moves      hard, right on sample one
    policy     rank whatever survives         soft, learned, improvable

Two properties fall out. A new rule changes behaviour IMMEDIATELY — no
retraining, no data, no loss curve. And the fraction of accuracy that
costs the most to train is precisely the sharp, rare, decidable kind
that a rule handles for free.
"""

from __future__ import annotations

from .. import (HeuristicPlayer, HybridPlayer, MinimaxPlayer, NeuralPlayer,
                RandomPlayer, agreement, duel, players)
from . import header, table


def main() -> int:
    header("E04 · a policy under hard constraints",
           "What do two rules buy a net that already agrees 83%?")

    rivals = (RandomPlayer(seed=1), HeuristicPlayer(), MinimaxPlayer())
    lost = lambda p: sum(duel(p, r, games=40, seed=4)[r.name] for r in rivals)

    rows = []
    for count in (10_000, 100_000, 300_000):
        net = NeuralPlayer(hidden=32).train(positions=count, rate=0.03)
        guarded = HybridPlayer(policy=net, intent="win")
        rows.append((f"{count:,}", f"{agreement(net):.0%}", f"{lost(net)}/120",
                     f"{agreement(guarded):.0%}", f"{lost(guarded)}/120"))
    table(rows, ("trained on", "policy agrees", "policy lost",
                 "+rules agrees", "+rules lost"))

    print("\n  Rules lift agreement at every training level — that part is")
    print("  reliable. They do NOT make a weak policy safe: they remove the")
    print("  immediate mistakes they encode and nothing deeper, so a policy")
    print("  that walks into a fork still loses. Strong policy + rules is")
    print("  what reaches never-loses; rules alone are not a safety net.\n")

    net = NeuralPlayer(hidden=32).train(positions=100_000, rate=0.03)
    guarded = HybridPlayer(policy=net, intent="win")
    guarded.move(*("X   O    ", "X"))
    print(f"  rules attached: {[r.__name__ for r in guarded.rules]}")
    print("\n  NOTE — rule_deny_the_fork is present and NOT trusted. It was")
    print("  written to fix a specific 30/180 loss cluster and did not move")
    print("  the number. Kept visible rather than deleted, because the")
    print("  diagnosis is unresolved and hiding it would lose the lead.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
