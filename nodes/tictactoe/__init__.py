"""tictactoe — a game as a NODE, not a module.

An element that merges into a larger brain rather than a thing in its
own right: the rules, and five interchangeable ways to choose a move.
It is here and not in `modules/` because nothing else would install it,
and not in `core/` because it is not app plumbing — it is a capability a
character can be given.

    from nodes.tictactoe import game, STRATEGIES
    player = STRATEGIES["minimax"]()

WHAT IT IS FOR. Tic-tac-toe is small enough to solve exactly, which
makes it a rare bench: every answer can be scored against a provably
correct one. So it is where "what should decide this?" gets measured
instead of argued — a hand-written ladder, an exhaustive search, a
language model, and a small trained net, all judged by one referee.
"""

from . import game
from .session import FACE_FOR, Move, Session
from .players import (
    HeuristicPlayer,
    HybridPlayer,
    LLMPlayer,
    MinimaxPlayer,
    NeuralPlayer,
    Player,
    RandomPlayer,
    agreement,
    duel,
    encode,
    evolve,
)

#: Every way to choose a square, by name. The Stage and the demos pick
#: from here, so adding a strategy is one entry and no UI change.
STRATEGIES = {
    "random": RandomPlayer,
    "heuristic": HeuristicPlayer,
    "minimax": MinimaxPlayer,
    "neural": NeuralPlayer,
    "hybrid": HybridPlayer,
    "llm": LLMPlayer,
}

__all__ = [
    "game", "STRATEGIES", "Player", "Session", "Move", "FACE_FOR",
    "RandomPlayer", "HeuristicPlayer", "MinimaxPlayer",
    "NeuralPlayer", "HybridPlayer", "LLMPlayer",
    "encode", "duel", "agreement", "evolve",
]
