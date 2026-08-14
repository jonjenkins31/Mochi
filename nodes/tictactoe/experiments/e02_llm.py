"""E02 — the language model. Can it play?

    python -m nodes.tictactoe.experiments.e02_llm

Loads a local GGUF and asks it for moves. No tools, no agent — a chat
model returning text, which is the honest baseline for "can the LLM just
do it?"

Findings this reproduces (gemma-4-E4B, temperature 0):

    legal        24/24   it never breaks the rules
    optimal       1/24   it almost never plays well
    forced blocks  2/5   it misses the one thing it must not
    squares used  1, 2, 4 — centre most of the time

It is not reading the board. It has a positional prior and picks from a
tiny set, which is why the moves look legal and play badly. Both halves
of that matter: the legality is genuinely reassuring, and the blindness
to the position is genuinely disqualifying for the DECISION.
"""

from __future__ import annotations

import collections
import os
import re

os.environ.setdefault("JAEGER_AGENT_NO_TOOLS", "1")

from .. import HeuristicPlayer, LLMPlayer, agreement, duel, game  # noqa: E402
from . import header, random, table  # noqa: E402


def main() -> int:
    from llama_cpp import Llama

    from modules import jaeger_agent as mind

    header("E02 · the language model",
           "Can a chat model with no tools choose a move?")
    path = mind.find_model()
    if not path:
        print("  no .gguf found — set $JAEGER_GGUF\n")
        return 2
    print(f"  loading {os.path.basename(path)} …", flush=True)
    llm = Llama(model_path=path, n_ctx=2048, n_gpu_layers=-1, verbose=False)

    def ask(prompt: str) -> str:
        return llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8, temperature=0.0)["choices"][0]["message"]["content"]

    player = LLMPlayer(ask)
    rng = random.Random(7)
    picks, illegal, optimal, total = collections.Counter(), 0, 0, 0
    for _ in range(24):
        board, mark = game.new_board(), "X"
        for _ in range(rng.choice((0, 2, 4))):
            if game.over(board):
                break
            board = game.place(board, rng.choice(game.legal(board)), mark)
            mark = "O" if mark == "X" else "X"
        if game.over(board):
            continue
        before = player.illegal
        square = player.move(board, mark)
        total += 1
        illegal += player.illegal - before
        picks[square] += 1
        optimal += square == game.best_move(board, mark)

    table([(f"{total - illegal}/{total}", f"{illegal}/{total}",
            f"{optimal}/{total}", ", ".join(map(str, sorted(picks))))],
          ("legal", "illegal", "optimal", "squares it ever chose"))

    print("\n  Forced blocks — the one thing it must not miss:")
    for board, mark in (("XX O     ", "O"), ("X   X    ", "O"),
                        ("X X O    ", "O"), ("  XX  O  ", "O")):
        said = player.move(board, mark)
        need = game.best_move(board, mark)
        print(f"    {board!r} as {mark}: said {said}, correct {need}  "
              f"{'✓' if said == need else '✗'}")

    print(f"\n  Overall agreement with perfect play: {agreement(player, 60):.0%}")
    tally = duel(player, HeuristicPlayer(), games=10, seed=1)
    print(f"  Against the E01 ladder, 10 games: {tally}")
    print("\n  Legal is not the same as competent. The next episodes try to")
    print("  buy competence without giving up the legality.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
