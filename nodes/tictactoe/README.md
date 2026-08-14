# tictactoe — teaching a robot to play, one method at a time

A **node**, not a module: an element that merges into a larger brain.
Nothing else would install it, and it is not app plumbing — it is a
capability a character can be given.

Tic-tac-toe is small enough to **solve exactly**, which makes it a rare
bench: every answer can be scored against a provably correct one. So it
is where "what should decide this?" gets measured instead of argued.

```
game.py        the rules — legality, wins, draws, and the value of
               every square. Code. Never learned, never guessed.
players.py     six ways to choose a square, behind one interface
experiments/   one question each, one command each
```

## The experiments

Each runs standalone — no app, no bus, no window:

```bash
python -m nodes.tictactoe.experiments.e01_rules
```

| | Question | What it shows |
|---|---|---|
| **E01** | How far does written-down code get you? | the ladder agrees with perfect play **48%** and never loses. Agreement ≠ skill |
| **E02** | Can a chat LLM play? | **24/24 legal, 1/24 optimal**, misses 3 of 5 forced blocks, only ever picks 3 squares |
| **E03** | What does training buy? | the curve — most skill early, the last few percent expensive, never reaches 100% |
| **E04** | What do rules buy a policy? | agreement **+10–18 points** at every level. Losses gone only when the policy is already strong |
| **E05** | Can it learn with no teacher? | bare evolution is slow and bad; **the same budget inside the rules** is fast and never loses |
| **E06** | Can it choose how hard to play? | one policy, three intents: opponent wins **0 / 23 / 46** out of 60 |

## The argument these build

1. **Rules are constraints; policies are preferences.** A constraint is
   right on the first sample. A preference is sometimes wrong no matter
   how long it trains.
2. **Known facts shrink the search.** E05 is the strongest result here:
   the same evolutionary budget, spent inside the rules, beats a run
   four times its size. You do not pay to rediscover what you know.
3. **Value, not randomness, is what makes softening believable.** E06
   only works because search already computed what every square is
   worth.

## What has NOT worked

Kept visible on purpose.

- `rule_deny_the_fork` — written to fix a 30/180 loss cluster. The
  number did not move and it cost games elsewhere, so it is **exported
  and off by default**. A rule is only right if it encodes something
  true, and "avoid positions from which a fork is reachable" is too
  blunt to be true. Constraints are cheap to add, not free to get right.
- **Rules are not a safety net for a weak policy.** They remove the
  mistakes they encode and nothing deeper. Strong policy + rules reaches
  never-loses; rules alone do not.

## Adding a method

One class with `.move(board, mark)`, one entry in `STRATEGIES`, one
experiment file. The bench (`duel`, `agreement`) judges anything that
implements the interface, so a new idea is measured against every
existing one on its first run.
