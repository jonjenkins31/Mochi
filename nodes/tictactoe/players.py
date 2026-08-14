"""Five ways to choose a square, behind one interface.

The point of this file is the COMPARISON. Tic-tac-toe is small enough to
solve exactly, which makes it a rare thing: a task where you can measure
a learned or generated answer against a provably correct one. So it is
the bench for "what should decide this?" — and every strategy here plays
by the same referee in `game.py`.

    random      no method at all — the floor
    heuristic   a hand-written ladder. Traditional, readable, beatable
    minimax     exhaustive. Provably optimal, the ceiling
    llm         ask a language model
    neural      a small net trained against minimax — the experiment

WHY A NET AT ALL, when minimax is already perfect. Because the question
is not "can we win tic-tac-toe". It is whether a learned policy can sit
between a rule and a language model: cheaper than search, steadier than
a prompt, and trainable on a task where the right answer is known. Nine
squares is the smallest honest place to try that.

PURE PYTHON, no numpy — 648 weights does not need a matrix library, and
a node that pulls one in is a node that cannot ship anywhere small.
"""

from __future__ import annotations

import json
import math
import pathlib
import random
from typing import Any, Protocol

from . import game


class Player(Protocol):
    """Anything that can take a turn."""

    name: str
    kind: str

    def move(self, board: str, mark: str) -> int:
        ...


# ── 1. no method at all ──────────────────────────────────────────

class RandomPlayer:
    """The floor. Every other strategy has to beat this to justify itself."""

    name = "random"
    kind = "traditional"

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def move(self, board: str, mark: str) -> int:
        return self._random.choice(game.legal(board))


# ── 2. a hand-written ladder ─────────────────────────────────────

class HeuristicPlayer:
    """The rules a person writes down: win, block, centre, corner, side.

    Traditional control logic — an ordered list of conditions, exactly
    the shape a PLC or a teach-pendant program would use. Readable,
    debuggable, and genuinely decent. It is also beatable, which is the
    honest reason more sophisticated methods exist.
    """

    name = "heuristic"
    kind = "traditional"

    def move(self, board: str, mark: str) -> int:
        other = "O" if mark == "X" else "X"
        for square in game.legal(board):                       # take a win
            if game.winner(game.place(board, square, mark)) == mark:
                return square
        for square in game.legal(board):                       # block a loss
            if game.winner(game.place(board, square, other)) == other:
                return square
        for square in (4, 0, 2, 6, 8, 1, 3, 5, 7):             # centre, corners, sides
            if board[square] == game.EMPTY:
                return square
        return game.legal(board)[0]


# ── 3. exhaustive search ─────────────────────────────────────────

class MinimaxPlayer:
    """The ceiling. Provably optimal, and the label source for training."""

    name = "minimax"
    kind = "traditional"

    def move(self, board: str, mark: str) -> int:
        return game.best_move(board, mark)


# ── 4. ask a language model ──────────────────────────────────────

class LLMPlayer:
    """Ask a model for a square, and REFUSE its answer if it is illegal.

    The fallback is not defensive padding — it is the finding. Measured
    on gemma-4-E4B: legal 24/24, optimal 1/24, forced blocks 2/5, and
    only ever squares 1, 2 or 4. A model produces plausible legal moves
    without reading the position, so a game that trusts it is a game
    nobody wants to play. Kept here so that stays visible rather than
    becoming folklore.
    """

    name = "llm"
    kind = "language model"

    PROMPT = ("You are playing tic-tac-toe as {mark}. {board}\\n"
              "Reply with ONLY the number of the square you take.")

    def __init__(self, ask: Any, fallback: Player | None = None) -> None:
        self._ask = ask                       # (prompt) -> str
        self._fallback = fallback or HeuristicPlayer()
        self.illegal = 0

    def move(self, board: str, mark: str) -> int:
        import re

        options = game.legal(board)
        try:
            reply = str(self._ask(self.PROMPT.format(
                mark=mark, board=game.describe(board))))
        except Exception:  # noqa: BLE001 — a slow brain must not stall a game
            reply = ""
        found = re.search(r"\d", reply)
        square = int(found.group()) if found else -1
        if square in options:
            return square
        self.illegal += 1
        return self._fallback.move(board, mark)


# ── 5. a small learned policy ────────────────────────────────────

def encode(board: str, mark: str) -> list[float]:
    """18 inputs: where I am, where they are.

    Two planes rather than one signed plane because "mine" and "theirs"
    are different features, and a net given +1/-1 has to spend capacity
    discovering that. Perspective-relative, so one net plays either side.
    """
    other = "O" if mark == "X" else "X"
    return ([1.0 if c == mark else 0.0 for c in board] +
            [1.0 if c == other else 0.0 for c in board])


class NeuralPlayer:
    """A 18-24-9 MLP trained to imitate minimax. The experiment.

    Sits deliberately between the two extremes: no search at inference
    (one forward pass, ~650 multiplies) and no prompt. Whether that is
    USEFUL is the open question — on nine squares minimax is already
    instant, so the value here is the bench, not the net.

    Illegal squares are masked before the argmax rather than trained
    away. A policy that has to learn the rules wastes capacity on the
    one part that is free, and would still be wrong sometimes; masking
    makes illegality structurally impossible.
    """

    name = "neural"
    kind = "neural network"

    def __init__(self, hidden: int = 24, seed: int = 0) -> None:
        self._random = random.Random(seed)
        self.hidden = hidden
        scale = 0.5
        self.w1 = [[self._random.uniform(-scale, scale) for _ in range(18)]
                   for _ in range(hidden)]
        self.b1 = [0.0] * hidden
        self.w2 = [[self._random.uniform(-scale, scale) for _ in range(hidden)]
                   for _ in range(9)]
        self.b2 = [0.0] * 9
        self.trained = 0

    # ── forward ──

    def _forward(self, x: list[float]) -> tuple[list[float], list[float]]:
        h = [math.tanh(sum(w * v for w, v in zip(row, x)) + b)
             for row, b in zip(self.w1, self.b1)]
        out = [sum(w * v for w, v in zip(row, h)) + b
               for row, b in zip(self.w2, self.b2)]
        return h, out

    def policy(self, board: str, mark: str) -> list[float]:
        """Softmax over legal squares — illegal ones get no probability."""
        _h, out = self._forward(encode(board, mark))
        options = set(game.legal(board))
        masked = [o if i in options else -1e9 for i, o in enumerate(out)]
        top = max(masked)
        exp = [math.exp(v - top) for v in masked]
        total = sum(exp) or 1.0
        return [v / total for v in exp]

    def move(self, board: str, mark: str) -> int:
        scores = self.policy(board, mark)
        return max(range(9), key=lambda i: scores[i])

    # ── training ──

    def learn(self, board: str, mark: str, target: int, rate: float) -> None:
        """One SGD step of cross-entropy against minimax's choice."""
        x = encode(board, mark)
        h, out = self._forward(x)
        options = set(game.legal(board))
        masked = [o if i in options else -1e9 for i, o in enumerate(out)]
        top = max(masked)
        exp = [math.exp(v - top) for v in masked]
        total = sum(exp) or 1.0
        probs = [v / total for v in exp]

        d_out = [p - (1.0 if i == target else 0.0) for i, p in enumerate(probs)]
        d_h = [0.0] * self.hidden
        for i in range(9):
            if i not in options:
                continue               # a masked logit has no gradient
            for j in range(self.hidden):
                d_h[j] += d_out[i] * self.w2[i][j]
                self.w2[i][j] -= rate * d_out[i] * h[j]
            self.b2[i] -= rate * d_out[i]
        for j in range(self.hidden):
            delta = d_h[j] * (1.0 - h[j] * h[j])
            for k in range(18):
                self.w1[j][k] -= rate * delta * x[k]
            self.b1[j] -= rate * delta
        self.trained += 1

    def train(self, positions: int = 4000, rate: float = 0.05,
              seed: int = 1) -> "NeuralPlayer":
        """Imitate minimax on positions reached by real play.

        Random boards would teach it positions no game reaches. Walking
        actual games — with some random moves mixed in so it sees more
        than the one perfect line — is what makes the training set
        resemble the task.
        """
        rng = random.Random(seed)
        seen = 0
        while seen < positions:
            board = game.new_board()
            mark = "X"
            while not game.over(board) and seen < positions:
                self.learn(board, mark, game.best_move(board, mark), rate)
                seen += 1
                square = (rng.choice(game.legal(board)) if rng.random() < 0.35
                          else game.best_move(board, mark))
                board = game.place(board, square, mark)
                mark = "O" if mark == "X" else "X"
        return self

    # ── persistence ──

    def save(self, path: Any) -> None:
        pathlib.Path(path).write_text(json.dumps({
            "hidden": self.hidden, "trained": self.trained,
            "w1": self.w1, "b1": self.b1, "w2": self.w2, "b2": self.b2}))

    @classmethod
    def load(cls, path: Any) -> "NeuralPlayer":
        data = json.loads(pathlib.Path(path).read_text())
        net = cls(hidden=int(data["hidden"]))
        net.w1, net.b1 = data["w1"], data["b1"]
        net.w2, net.b2 = data["w2"], data["b2"]
        net.trained = int(data.get("trained", 0))
        return net


# ── the bench ────────────────────────────────────────────────────

def duel(first: Player, second: Player, games: int = 50,
         seed: int = 0) -> dict[str, int]:
    """Play them against each other, alternating who starts.

    Alternating matters: going first in tic-tac-toe is a real advantage,
    and a bench that ignores it measures the coin toss.
    """
    rng = random.Random(seed)
    tally = {first.name: 0, second.name: 0, "draw": 0}
    for n in range(games):
        board = game.new_board()
        players = {"X": first, "O": second} if n % 2 == 0 else {"X": second, "O": first}
        mark = "X"
        while not game.over(board):
            try:
                square = players[mark].move(board, mark)
            except Exception:  # noqa: BLE001
                square = rng.choice(game.legal(board))
            if square not in game.legal(board):
                square = rng.choice(game.legal(board))
            board = game.place(board, square, mark)
            mark = "O" if mark == "X" else "X"
        champion = game.winner(board)
        tally["draw" if not champion else players[champion].name] += 1
    return tally


def agreement(player: Player, positions: int = 300, seed: int = 5) -> float:
    """How often it picks what minimax would — 1.0 is perfect play."""
    rng = random.Random(seed)
    hits = total = 0
    while total < positions:
        board = game.new_board()
        mark = "X"
        while not game.over(board) and total < positions:
            if player.move(board, mark) == game.best_move(board, mark):
                hits += 1
            total += 1
            board = game.place(board, rng.choice(game.legal(board)), mark)
            mark = "O" if mark == "X" else "X"
    return hits / total if total else 0.0


__all__ = ["Player", "RandomPlayer", "HeuristicPlayer", "MinimaxPlayer",
           "LLMPlayer", "NeuralPlayer", "HybridPlayer", "encode", "duel",
           "agreement", "evolve", "rule_take_the_win", "rule_block_the_loss",
           "rule_deny_the_fork"]


# ── 6. the hybrid: a policy under hard constraints ───────────────

class HybridPlayer:
    """A learned preference, vetoed by rules that cannot be argued with.

    THE ARGUMENT, from this file's own bench: the hand-written ladder
    agrees with perfect play only 48% of the time and never loses; the
    trained net agrees 83% and loses to RANDOM. Agreement is not safety.
    A policy is a preference — soft, probabilistic, and wrong sometimes
    no matter how long it trains. A rule is a constraint, and it is
    right on the first sample.

    So they are stacked rather than blended:

        rules      remove moves that are provably wrong   ← hard, instant
        policy     rank whatever survives                 ← learned, soft

    Two properties follow, and they are the reasons to want this:

    · A NEW RULE CHANGES BEHAVIOUR IMMEDIATELY. No retraining, no data,
      no waiting for a loss curve. Add "never take a corner opposite
      theirs" and the next move obeys it. That is not something you can
      do to a set of weights.

    · THE LAST FRACTION OF ACCURACY IS FREE. Getting a net from 99% to
      99.999% by training is the expensive part of machine learning and
      it is exactly the part rules hand over for nothing — because the
      cases a policy gets wrong last are the sharp, rare, decidable
      ones, which is precisely what a rule is good at.

    The net still earns its place: where the rules are SILENT — most of
    the midgame — its ranking is what plays, and it plays better than
    the ladder's fixed square order.
    """

    name = "hybrid"
    kind = "neural + rules"

    #: How hard to play. The rules are absolute either way — this
    #: chooses among moves that are all legal and all understood.
    #:
    #:   "win"      take the best value available. The opponent loses.
    #:   "even"     take the best move that does not force a win —
    #:              plays properly, does not run away with it
    #:   "let"      concede: prefer a move that leaves THEM a way back
    #:
    #: The distinction that makes this worth having: a softened move is
    #: CHOSEN by value, not randomised. A random bad move looks broken
    #: and reads as a bug; the second-best move reads as a person going
    #: easy on you, which is the thing you actually want when playing
    #: with a child.
    INTENTS = ("win", "even", "let")

    def __init__(self, policy: Any | None = None,
                 rules: list | None = None, intent: str = "win") -> None:
        self.intent = intent if intent in self.INTENTS else "win"
        self.policy_net = policy or NeuralPlayer()
        #: Constraints, in order. Each returns a narrowed list of squares
        #: — never an empty one, so a rule can prefer without forbidding.
        self.rules = rules if rules is not None else (
            [rule_take_the_win, rule_block_the_loss] if intent == "win"
            else [rule_take_the_win] if intent == "even"
            else [])          # conceding: no rule should rescue the game
        self.vetoes = 0

    def move(self, board: str, mark: str) -> int:
        options = self._allowed(board, mark)
        scores = self.policy_net.policy(board, mark)
        best = max(options, key=lambda square: scores[square])
        if best != max(range(9), key=lambda i: scores[i]):
            self.vetoes += 1        # the rules overrode the net's own pick
        return best

    def _allowed(self, board: str, mark: str) -> list[int]:
        """Narrow the legal moves by INTENT first, then by the rules.

        Order matters. Intent decides what kind of game this is; rules
        then keep it a real game — even conceding, it will not hand over
        a win it was never threatened with, because a character that
        plays obviously badly is not being kind, it is being broken.
        """
        options = game.legal(board)
        if self.intent != "win":
            valued = game.rank(board, mark)
            if self.intent == "even":
                # anything that is not a forced win: play properly,
                # do not run away with it
                softened = [s for s, v in valued if v <= 0] or [valued[0][0]]
            else:                        # "let" — leave them a way back
                softened = [s for s, v in valued if v < 0] or \
                           [s for s, v in valued if v == 0] or [valued[-1][0]]
            options = softened
        for rule in self.rules:
            narrowed = rule(board, mark, options)
            if narrowed and narrowed != options:
                options = narrowed
        return options or game.legal(board)


def rule_take_the_win(board: str, mark: str, options: list[int]) -> list[int]:
    """If a square wins now, nothing else is worth considering."""
    wins = [s for s in options
            if game.winner(game.place(board, s, mark)) == mark]
    return wins or options


def rule_block_the_loss(board: str, mark: str, options: list[int]) -> list[int]:
    """If they win next move unless you take a square, take it."""
    other = "O" if mark == "X" else "X"
    blocks = [s for s in options
              if game.winner(game.place(board, s, other)) == other]
    return blocks or options


# ── learning without labels: evolution ───────────────────────────

def evolve(population: int = 24, generations: int = 30, games: int = 12,
           hidden: int = 24, mutation: float = 0.35, seed: int = 0,
           opponent: Any = None, with_rules: bool = False) -> NeuralPlayer:
    """Breed a policy from GAME OUTCOMES — no minimax, no labels.

    The other half of the answer to "must a net see millions of
    examples?". Imitation needs a teacher that already knows; evolution
    needs only a scoreboard, which is the situation you are actually in
    for anything worth automating. Nobody can label the right servo
    angle for "look pleased"; anybody can say which of two attempts
    looked better.

    Deliberately the simplest thing that is honestly evolutionary:
    mutate, play, keep the top half, repeat. No crossover, no fancy
    selection — those are optimisations, and this is a demonstration
    that the SIGNAL is sufficient.
    """
    rng = random.Random(seed)
    rival = opponent or HeuristicPlayer()

    def mutant(parent: NeuralPlayer, strength: float) -> NeuralPlayer:
        child = NeuralPlayer(hidden=parent.hidden, seed=rng.randrange(1 << 30))
        child.w1 = [[w + rng.gauss(0, strength) for w in row] for row in parent.w1]
        child.b1 = [b + rng.gauss(0, strength) for b in parent.b1]
        child.w2 = [[w + rng.gauss(0, strength) for w in row] for row in parent.w2]
        child.b2 = [b + rng.gauss(0, strength) for b in parent.b2]
        return child

    def fitness(net: NeuralPlayer) -> float:
        """A draw is a success at tic-tac-toe — perfect play draws
        perfect play — so losses are what get punished.

        `with_rules` evaluates each candidate INSIDE the hybrid, which
        is the interesting experiment: the rules already know legality
        and immediate tactics, so no generation is spent rediscovering
        them and the fitness signal is about the part actually being
        learned. Known facts do not just make the player safer — they
        make the SEARCH cheaper, because the space being searched is
        smaller.
        """
        candidate = HybridPlayer(policy=net, intent="win") if with_rules else net
        tally = duel(candidate, rival, games=games, seed=rng.randrange(1 << 20))
        mine = tally.get(candidate.name, 0)
        return mine * 1.0 + tally["draw"] * 0.5 - tally[rival.name]

    pool = [NeuralPlayer(hidden=hidden, seed=rng.randrange(1 << 30))
            for _ in range(population)]
    for generation in range(generations):
        ranked = sorted(pool, key=fitness, reverse=True)
        keep = ranked[: max(2, population // 2)]
        strength = mutation * (1.0 - generation / max(1, generations))
        pool = keep + [mutant(rng.choice(keep), strength)
                       for _ in range(population - len(keep))]
    return sorted(pool, key=fitness, reverse=True)[0]


def rule_deny_the_fork(board: str, mark: str, options: list[int]) -> list[int]:
    """Do not hand them a square from which they get TWO threats.

    NOT IN THE DEFAULT SET — it measurably hurts. Added after the bench found it. Two rules — take the win, block the
    loss — removed every immediate loss and still lost 30 games in 180,
    because a fork is not an immediate loss: it is a move that makes two
    of them, and by the time either shows up it is unanswerable.

    AND IT DID NOT WORK. The loss cluster it was written for did not
    move (30/180 before and after), and it cost games elsewhere — with
    it enabled a 10k policy loses 20/120 where two rules lose none. So
    it is kept, exported, and switched OFF: pass it explicitly to
    experiment with. The lesson is the honest half of the hybrid claim —
    a rule is only right if it encodes something true, and "avoid
    positions from which a fork is reachable" is too blunt to be true.
    Constraints are cheap to add and not free to get right.
    """
    other = "O" if mark == "X" else "X"

    def threats(state: str, who: str) -> int:
        return sum(1 for s in game.legal(state)
                   if game.winner(game.place(state, s, who)) == who)

    safe = []
    for square in options:
        after = game.place(board, square, mark)
        if game.over(after):
            safe.append(square)
            continue
        # could they reply in a way that leaves them two winning squares?
        forks = any(threats(game.place(after, reply, other), other) >= 2
                    for reply in game.legal(after))
        if not forks:
            safe.append(square)
    return safe or options
