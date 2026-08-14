"""Tic-tac-toe — where the logic lives, measured rather than assumed.

Run it:  ./venv/bin/python dev/demos/tictactoe_demo.py

WHAT THIS DEMO IS FOR. "Should the LLM do this?" is answerable, and the
answer for a game is not the one people expect. Measured against
gemma-4-E4B (tool-less chat, temperature 0):

    legal moves          24/24   it never breaks the rules
    optimal moves         1/24   it almost never plays well
    forced blocks         2/5    it misses the one thing it must not
    squares ever chosen   1, 2, 4 — centre 10/18 times

It is not reasoning about the position. It has a positional prior —
centre is good — and picks from a tiny set, which is why the moves look
legal and play badly. A game where the opponent misses three blocks in
five is not a game.

SO THE SPLIT IS NOT A MATTER OF TASTE:

    rules, legality, win/draw   code. Non-negotiable.
    which square to take        code. Minimax, exact, sub-millisecond.
    what just happened          code. `threat()` returns a WORD.
    what to SAY about it        the model. Only it can do this.
    which face to pull          either — the model picks well from a word

The last two are the model's real job, and it is good at them. Asked to
be dramatic about "+7" it writes nonsense; asked to react to "about to
lose" it writes something a character would say.

NO TOOLS ANYWHERE IN HERE. The model is never asked to DO anything, only
to say something about a state that code computed. That is the shape
that works on a 4B, and it is why `[config.mind] tools` stays false.
"""

from __future__ import annotations

import os
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ.setdefault("JAEGER_AGENT_NO_TOOLS", "1")

from core import expressive, tictactoe as ttt  # noqa: E402
from modules import jaeger_agent as mind  # noqa: E402

#: The character's read on the position, before it says a word. A face
#: is a reaction and reactions are fast — deriving it from the same word
#: the model gets keeps them agreeing even when inference is slow.
FACE_FOR = {
    "won": "happy", "lost": "sad", "drew": "neutral",
    "about to win": "happy", "about to lose": "look_down", "even": "neutral",
}

BANTER = (
    "You are Bitmap Man, two monochrome eyes playing tic-tac-toe against a "
    "person. You just played {square}. The game is: {state}. Say ONE short "
    "line about it, in character. Begin with one of these in square "
    "brackets: {faces}."
)


def main() -> int:
    from llama_cpp import Llama

    faces = ("neutral", "happy", "closed", "look_down", "sad", "look_up")
    print("loading the model…", flush=True)
    llm = Llama(model_path=mind.find_model(), n_ctx=2048,
                n_gpu_layers=-1, verbose=False)

    def banter(square: int, state: str) -> tuple[str, str]:
        out = llm.create_chat_completion(
            messages=[{"role": "user", "content": BANTER.format(
                square=square, state=state, faces=", ".join(faces))}],
            max_tokens=48, temperature=0.7)
        return expressive.split(
            out["choices"][0]["message"]["content"].strip(), faces)

    random.seed(3)
    board = ttt.new_board()
    me, you = "X", "O"
    print("\nBitmap Man is X. You are O. (Your moves are random here.)\n")

    while not ttt.over(board):
        # ── the agent's move: CODE decides ──
        square = ttt.best_move(board, me)
        board = ttt.place(board, square, me)
        state = ttt.threat(board, me)
        # the face comes from the same word, instantly
        face = FACE_FOR.get(state, "neutral")
        # ── the agent's line: the MODEL decides ──
        chosen, line = banter(square, state)
        print(f"  Bitmap Man plays {square}   [{state}]")
        print(f"    face  {chosen or face}{'  (model)' if chosen else '  (code)'}")
        print(f"    says  {line!r}")
        if ttt.over(board):
            break

        # ── your move ──
        yours = random.choice(ttt.legal(board))
        board = ttt.place(board, yours, you)
        print(f"  You play {yours}\n")

    print(ttt.render(board))
    result = ttt.winner(board)
    print(f"\n  {'Bitmap Man wins' if result == me else 'You win' if result else 'A draw'}")
    print("\n  Every move above was chosen by minimax. Every line was "
          "written by the model.\n  Neither could have done the other's job.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
