"""Runnable experiments — one question each, one command each.

    python -m nodes.tictactoe.experiments.e01_rules
    python -m nodes.tictactoe.experiments.e02_llm
    python -m nodes.tictactoe.experiments.e03_neural
    python -m nodes.tictactoe.experiments.e04_hybrid
    python -m nodes.tictactoe.experiments.e05_evolution
    python -m nodes.tictactoe.experiments.e06_intent

Each is standalone: no app, no bus, no window. Import nothing from
`interfaces/` and nothing from Qt — an experiment you cannot run headless
is one you cannot run on a build box, in a notebook, or over ssh, which
is most of the places research actually happens.

They are numbered because they build on each other, and they print
NUMBERS rather than claims. Anything asserted in a docstring here should
be reproducible by running the file.
"""

import random
import time
from typing import Any


def header(title: str, question: str) -> None:
    print(f"\n\033[1m{title}\033[0m")
    print(f"  {question}\n" + "  " + "─" * 62)


def table(rows: list[tuple], columns: tuple[str, ...]) -> None:
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) + 2
              for i, c in enumerate(columns)]
    print("  " + "".join(str(c).ljust(w) for c, w in zip(columns, widths)))
    for row in rows:
        print("  " + "".join(str(v).ljust(w) for v, w in zip(row, widths)))


def timed(work: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    return work(), time.perf_counter() - start


__all__ = ["header", "table", "timed", "random"]
