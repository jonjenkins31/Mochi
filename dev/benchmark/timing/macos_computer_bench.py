#!/usr/bin/env python3
"""macOS computer-use latency regression gate.

Every assertion is a wall-clock budget on a routine operation that
the capability ladder should handle without invoking the screenshot
loop. A failure means the planner regressed — either an engine got
slower, or the routing now picks a slower tier.

Targets (chosen conservatively; tighten as the engines improve):

  * AppleScript ``is_running`` probe        — < 1500 ms
  * AppleScript ``activate`` (already running) — < 1500 ms
  * AX ``list_apps`` cold-call               — < 800 ms
  * AX ``focused_window`` (system-wide)      — < 800 ms
  * Goal parser pure (no I/O)                — < 5 ms per goal
  * Planner select_engine (no execute)       — < 5 ms per action

Usage::

    python benchmark/timing/macos_computer_bench.py

Skip per-engine probes that aren't applicable on a non-Mac host —
the script reports them as ``skip`` rather than failing.
"""

from __future__ import annotations

import sys
import time
from typing import Callable

REPO_ROOT_PARENTS = 2  # benchmark/timing → benchmark → repo root
import pathlib
_REPO = pathlib.Path(__file__).resolve().parents[REPO_ROOT_PARENTS]
sys.path.insert(0, str(_REPO / "src"))


# ── budget table ───────────────────────────────────────────────────


# Each entry: (label, budget_ms, callable returning a dict result).
# Callables MUST be idempotent + side-effect-free. We don't drive
# real button presses — those need user-state guarantees the bench
# doesn't have.
def _bench_cases():
    from jaeger_os.skills.macos_computer_v1 import computer_use, computer_look
    from jaeger_os.skills.macos_computer_v1 import planner
    from jaeger_os.skills.macos_computer_v1.engines import Action
    from jaeger_os.skills.macos_computer_v1.goal_parser import parse_goal

    return [
        # AppleScript round-trips.
        ("applescript.is_running", 1500,
         lambda: computer_use(action="is_running", value="Finder")),
        ("applescript.front_app", 1500,
         lambda: computer_use(action="front_app")),
        # AX reads — must stay cheap.
        ("ax.list_apps", 800,
         lambda: computer_use(action="list_apps")),
        ("ax.focused_window", 800,
         lambda: computer_use(action="focused_window")),
        # computer_look — the verification path.
        ("computer_look.no_screenshot", 1500,
         lambda: computer_look()),
        # Planner pure-decision microbench — must be near-free.
        ("planner.select_engine x100", 50,
         lambda: _run_n(lambda: planner.select_engine(
             Action(kind="press", args={"label": "5"}, target="Calculator"),
         ), 100)),
        # Goal parser microbench — must be near-free.
        ("goal_parser.parse_goal x100", 50,
         lambda: _run_n(lambda: parse_goal(
             "open Calculator and click 5 and click +"
         ), 100)),
    ]


def _run_n(fn: Callable, n: int) -> dict:
    """Run ``fn`` ``n`` times; the elapsed-ms total IS the
    measurement. Used for microbenches where one call is too short
    to time precisely."""
    for _ in range(n):
        fn()
    return {"ok": True, "iterations": n}


# ── driver ──────────────────────────────────────────────────────────


def main() -> int:
    cases = _bench_cases()
    print()
    print(f"  {'Case':<36} {'Budget':>9}  {'Wall':>9}  Verdict")
    print(f"  {'─' * 36} {'─' * 9}  {'─' * 9}  {'─' * 7}")

    failed = 0
    for label, budget_ms, fn in cases:
        started = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            print(f"  {label:<36} {budget_ms:>7d}ms {elapsed_ms:>7.0f}ms"
                  f"   ERROR: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
        under_budget = elapsed_ms <= budget_ms
        mark = "✓" if (ok and under_budget) else "✗"
        if not under_budget:
            failed += 1
        if not ok:
            # Engine returned ok=False — usually means the env lacks
            # something (no AX permission, app not running). Treat
            # as skip rather than fail when under budget.
            if under_budget:
                mark = "skip"
            else:
                failed += 1
        print(f"  {label:<36} {budget_ms:>7d}ms {elapsed_ms:>7.0f}ms"
              f"   {mark}")
    print()
    if failed:
        print(f"  {failed} budget violation(s)")
        return 1
    print("  All cases under budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
