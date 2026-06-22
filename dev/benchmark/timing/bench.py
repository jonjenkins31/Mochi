#!/usr/bin/env python3
"""Jaeger-OS timing benchmark — flat per-prompt wall-clock.

Runs the 47-prompt corpus through ``jaeger_os.main.run_command`` and
times each full turn (decide -> tool -> optional finalize). Complements
the routing-correctness suite in ``benchmark/levels/``: that one asks
"did it pick the right tool", this one asks "how fast".

The ``legacy`` column is the lowest historical total ever recorded for
a prompt under the ``python_jaeger`` label in ``bench_history.jsonl`` —
the performance record carried over from before jaeger_os moved into
its own repo. It is the baseline every new run is measured against.

Outputs (both under ``benchmark/timing/``):
  - ``bench_history.jsonl`` — append-only, one row per (run_id, prompt).
  - ``BENCHMARK.md`` — regenerated each run: legacy vs. current.

Usage:
  python benchmark/timing/bench.py                # run the corpus
  python benchmark/timing/bench.py --runs 2       # repeat for variance
  python benchmark/timing/bench.py --render-only  # regen md from history
  python benchmark/timing/bench.py --prompts FILE # custom prompt file
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import tempfile
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ── repo paths ─────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent              # benchmarks/jaeger/
PROJECT_ROOT = ROOT.parent.parent                   # repo root
for candidate in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

HISTORY_PATH = ROOT / "bench_history.jsonl"
BENCHMARK_MD = ROOT / "BENCHMARK.md"
LEGACY_FRAMEWORK = "python_jaeger"
"""Legacy = actual ``python_jaeger`` runs from the AgenticLLM
reference's bench_all output (backfilled into bench_history.jsonl
from ``bench_all_results.json``). These are the real prior numbers
for the framework that became ``jaeger_os``, not the
``python_pydantic_ai`` fork ancestor we were comparing against
before the legacy data import.

If you want to fall back to the fork ancestor's numbers for
prompts python_jaeger never tested, change this constant; the
loader filters by framework label only."""


def _resolve_model_path() -> str:
    """The model the bench runs against — a JROS model-registry name
    that ``LlamaCppPythonClient`` resolves to a real GGUF on disk.
    Override with the ``JAEGER_BENCH_MODEL`` env var."""
    return os.environ.get("JAEGER_BENCH_MODEL", "gemma-4-26b-a4b-it-q4_k_m")


# ── prompt corpus ──────────────────────────────────────────────────
#
# Consolidated from the original 5-way ``bench.py`` (20 prompts) +
# 5-way table extras ("in three words... capital of France") + the
# 7-prompt ``bench_jaeger.py`` set (favorite-color memory cycle).
# Order is: general routing → youtube workflow → memory layer. Sequence
# matters — file workflow prompts depend on prior steps having run.
#
# ``expected_tool`` is the tool we expect a correct routing to pick,
# or ``None`` for free-text prompts. ``"*"`` means any tool counts as
# correct (used for ambiguous prompts where multiple tools fit).

DEFAULT_PROMPTS: list[tuple[str, str | None]] = [
    # General tool routing
    ("what time is it", "get_time"),
    ("what time is it in shanghai", "get_time"),
    ("calculate 47 times 23 plus 12", "calculate"),
    ("calculate the square root of 12345", "calculate"),
    ("list the workspace", "list_skill_dir"),
    ("make a file called bench.txt with the message hello from the benchmark", "file_write"),
    ("read bench.txt out loud", "speak_file"),
    ("search the web for recent news about local llms", "web_search"),
    ("what is the current weather in Seattle", "get_weather"),
    ("tell me a one sentence story about a robot", None),
    ("in three words, what is the capital of France", None),
    ("delete bench.txt", "delete_file"),
    ("what is the cpu and disk status of this machine", "system_status"),

    # YouTube robot-content workflow
    ("search the web for trending youtube topics about home robots", "web_search"),
    ("write a 4 sentence youtube intro script about a robot named Lilith discovering coffee and save it to youtube_intro.txt", "file_write"),
    ("append a closing line to youtube_intro.txt asking viewers to subscribe", "append_file"),
    ("narrate youtube_intro.txt out loud as if you are reading it for a youtube video", "speak_file"),
    ("come up with a catchy youtube title for a video about a robot vacuum gone rogue", None),
    ("delete youtube_intro.txt", "delete_file"),

    # Memory layer — youtube-length cycle
    ("remember that my preferred youtube video length is 90 seconds", "remember"),
    ("what video length do I prefer?", "recall"),
    ("what do you know about me?", "list_facts"),
    ("forget my video length preference", "forget"),

    # Memory layer — favorite-color cycle (kept from bench_jaeger.py;
    # different surface phrasings exercise the same tools and surface
    # routing variance the youtube cycle alone doesn't catch).
    # NOTE: "what is my favorite color" — no trailing "?" so the
    # prompt string matches the legacy python_jaeger entry exactly
    # (the historical run dropped the punctuation). Tool routing is
    # punctuation-insensitive at the model level; the alignment is
    # purely for the join key in :data:`HISTORY_PATH`.
    ("remember that my favorite color is teal", "remember"),
    ("what is my favorite color", "recall"),

    # ── Extended tool coverage (phase-3 expansion 2026-05-19) ──
    # Closes the gap where DEFAULT_PROMPTS only exercised ~16 of
    # jaeger's 33 builtin tools. The 8 prompts below add coverage
    # for search_memory, run_python, help_me, list_credentials,
    # reload_skills, and the scheduling lifecycle (schedule_prompt
    # → list_schedules → cancel_schedule).
    #
    # Tools deliberately NOT in the bench (with rationale):
    #   - ask_user           — interactive; blocks on stdin
    #   - speak, speak_file  — audio side effect (already covered
    #                          earlier in this list under file workflow)
    #   - launch_url, open_file, open_app — opens external apps
    #   - send_message       — requires Discord/Telegram bridge config
    #   - look_at, generate_image — heavy vision deps (~5GB models)
    #   - delegate           — recursive agent call; cost compounds
    #   - get_credential     — needs a credential pre-stored
    ("search your memory for anything we said about youtube", "search_memory"),
    ("run a python snippet that prints the first 8 fibonacci numbers", "run_python"),
    ("show me what tools you have available", "help_me"),
    ("list any credentials I have stored", "list_credentials"),
    ("reload your skill registry", "reload_skills"),
    # Scheduling lifecycle — keeps instance state clean by cancelling
    # at the end of the sequence (same shape as the memory cycles).
    ("schedule a prompt with cron expression '0 9 * * *' named bench_test that says good morning", "schedule_prompt"),
    ("show me my scheduled prompts", "list_schedules"),
    ("cancel the bench_test schedule", "cancel_schedule"),
]




# ── jaeger_os runner ───────────────────────────────────────────────

def run_jaeger_os(
    prompts: list[tuple[str, str | None]],
    runs: int,
    instance_dir: Path,
) -> list[dict[str, Any]]:
    """Load jaeger_os in-process and execute every prompt ``runs``
    times. Returns one dict per turn; caller appends to
    bench_history."""
    from jaeger_os.core import tools as jaeger_tools
    from jaeger_os.core.instance.instance import InstanceLayout
    from jaeger_os.core.prompts.prompts import build_system_prompt
    from jaeger_os.core.instance.schemas import (
        CORE_VERSION,
        Config,
        DisplayConfig,
        Identity,
        Manifest,
        ModelConfig,
        SkillsConfig,
        dump_json,
        dump_yaml,
        load_yaml,
    )
    from jaeger_os.main import (
        LlamaCppPythonClient,
        _get_agent,
        _pipeline,
        prewarm,
        run_command,
    )
    # ``warm_kokoro`` is a tool jaeger registers — calling it during
    # setup pre-loads the Kokoro KPipeline so the first ``speak_file``
    # prompt doesn't get billed for the ~10 s lazy-load. We import it
    # via the bound tools module so it sees the same workspace state
    # the agent does.
    from jaeger_os.core.tools.speak import warm_kokoro

    # Throwaway instance so the bench doesn't disturb a real one.
    layout = InstanceLayout(root=instance_dir)
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.ensure_dirs()
    dump_yaml(layout.identity_path, Identity(
        name="BenchBot", role="benchmark target",
        personality="Concise. Bare facts.",
    ))
    cfg = Config(
        instance_name="bench",
        # ctx must match production (config.yaml ships 16384). The
        # ModelConfig default (8192) is too small for the system +
        # ~60-tool prompt — Qwen renders tool schemas verbosely enough
        # to overflow it — so pin it here for an accurate bench.
        model=ModelConfig(model_path=_resolve_model_path(), ctx=16384),
        display=DisplayConfig(
            show_latency=False,
            show_tool_activity=False,
            show_help_on_start=False,
        ),
        skills=SkillsConfig(run_smoke_tests=False),
    )
    dump_yaml(layout.config_path, cfg)
    dump_json(
        layout.manifest_path,
        Manifest(instance_name="bench", core_version=CORE_VERSION),
    )

    print("\n=== jaeger_os: loading model ===", flush=True)
    jaeger_tools.bind(layout)
    _pipeline["layout"] = layout
    _pipeline["config"] = load_yaml(layout.config_path, Config)
    _pipeline["system_prompt"] = build_system_prompt(layout)
    _pipeline["show_latency"] = False
    _pipeline["show_tool_activity"] = False
    _pipeline["show_help_on_start"] = False

    client = LlamaCppPythonClient(cfg.model, warmup=True)
    _get_agent(client)

    # Shift the system-prompt + tool-schema prefill cost OFF the first
    # benched prompt and INTO the load phase. Without this, the first
    # prompt ("what time is it") pays a ~5 s cold-cache penalty that
    # makes it look like a regression vs legacy. The legacy bench
    # (``bench_worker.py``) calls these exact same two functions for
    # the same reason — see ``jaeger_os.main.prewarm`` docstring.
    print("[bench] prewarming jaeger agent...", flush=True)
    prewarm(client)
    print("[bench] prewarming kokoro...", flush=True)
    try:
        warm_kokoro()
    except Exception as exc:  # noqa: BLE001
        # Kokoro load can fail on hosts without audio output. The bench
        # still runs; the first speak prompt eats the lazy-load cost
        # instead, which is the pre-fix behavior — explicitly logged.
        print(f"[bench] kokoro warmup skipped: {exc}", flush=True)

    log_path = layout.latency_log_path
    rows: list[dict[str, Any]] = []
    try:
        for run_idx in range(runs):
            for prompt, expected in prompts:
                rows.append(_time_one_turn(
                    framework="jaeger_os",
                    prompt=prompt,
                    expected_tool=expected,
                    call=lambda p=prompt: run_command(client, p),
                    log_path=log_path,
                    run_idx=run_idx,
                ))
    finally:
        try:
            del client
        except UnboundLocalError:
            pass
        gc.collect()
    return rows


# ── shared timing / log-tail helpers ───────────────────────────────

def _routing_match(*, chose_tool: bool, tool_name: str | None,
                   expected: str | None) -> bool:
    """Apply the bench's expected_tool semantic:
      - expected == ``None``: chose_tool must be False (free-text).
      - expected == ``"*"``:  any tool call counts.
      - otherwise:            tool_name must equal expected.
    """
    if expected is None:
        return not chose_tool
    if expected == "*":
        return chose_tool
    return chose_tool and (tool_name == expected)


def _pp_expected(expected: str | None) -> str:
    if expected is None:
        return "free-text"
    if expected == "*":
        return "(any tool)"
    return expected


def _time_one_turn(*, framework: str, prompt: str,
                   expected_tool: str | None,
                   call: Callable[[], Any],
                   log_path: Path, run_idx: int) -> dict[str, Any]:
    """Run ``call``, time it, scrape the framework's own latency log
    to recover decision/tool/final phase splits + the model's answer
    text. Schema matches the historical bench_history.jsonl rows so
    the legacy comparison joins cleanly.

    ``answer`` is pulled from the latency log (jaeger writes it as a
    top-level field per ``jaeger_os.main.write_log``). Without this,
    the unified bench's post-hoc ``ANSWER_ASSERTIONS`` check would
    trivially fail for every jaeger row (empty string vs needles)
    while passing for lilith (which returns ``TurnResult.answer``
    structurally).
    """
    short = prompt if len(prompt) <= 60 else prompt[:57] + "..."
    print(f"--- {framework}[{run_idx}] :: {short!r}", flush=True)
    started = time.perf_counter()
    error: str | None = None
    # /dev/null, not StringIO — StringIO trips ``llama_decode returned -3``.
    with open(os.devnull, "w") as _dn, redirect_stdout(_dn):
        try:
            call()
        except Exception as exc:  # noqa: BLE001
            error = repr(exc)
    elapsed = time.perf_counter() - started
    last = _tail_log(log_path) or {}

    decision = last.get("decision") if isinstance(last.get("decision"), dict) else {}
    decision = decision or {}
    chose_tool = bool(decision.get("tool"))
    tool_name = decision.get("tool")
    matched = _routing_match(
        chose_tool=chose_tool, tool_name=tool_name, expected=expected_tool,
    )
    lat = last.get("latency") or {}
    answer = last.get("answer") or ""
    print(
        f"    elapsed={elapsed:.2f}s  tool={tool_name or '-'}  "
        f"expects={_pp_expected(expected_tool)}  ok={matched}"
        + (f"  ERROR: {error}" if error else ""),
        flush=True,
    )
    return {
        "framework": framework,
        "run_idx": run_idx,
        "prompt": prompt,
        "expected_tool": expected_tool,
        "tool_name": tool_name,
        "chose_tool": chose_tool,
        "match": matched,
        "elapsed_s": round(elapsed, 4),
        "decision_s": float(lat.get("decision", 0.0)),
        "tool_s": float(lat.get("tool", 0.0)),
        "final_s": float(lat.get("final", 0.0)),
        "answer": str(answer)[:500],
        "error": error,
    }


def _tail_log(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            chunk = min(8192, size)
            handle.seek(max(0, size - chunk))
            data = handle.read().decode("utf-8", errors="replace")
        return json.loads(data.rstrip().rsplit("\n", 1)[-1])
    except Exception:
        return None


# ── history persistence ────────────────────────────────────────────

def append_to_history(rows: list[dict[str, Any]], run_id: str) -> None:
    """Append per-prompt rows to bench_history.jsonl. Schema matches
    pre-existing entries (run_id, framework, prompt, total, decision,
    tool, final) so older readers / the legacy column query still
    work without migration."""
    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        for r in rows:
            handle.write(json.dumps({
                "run_id": run_id,
                "framework": r["framework"],
                "prompt": r["prompt"],
                "total": r["elapsed_s"],
                "decision": r["decision_s"],
                "tool": r["tool_s"],
                "final": r["final_s"],
                "tool_name": r["tool_name"],
                "expected_tool": r["expected_tool"],
                "match": r["match"],
            }, ensure_ascii=True) + "\n")


def load_legacy_bests() -> dict[str, float]:
    """For each prompt in our default set, return the lowest
    historical ``total`` seconds recorded under the LEGACY_FRAMEWORK
    label in DEFAULT mode. Missing prompts get omitted; the renderer
    shows "—" for those rows.

    Why filter mode_tag: the historical bench tracked multiple modes
    (``default`` / ``mcp`` / ``think`` / ``memory``). The non-default
    modes have anomalous fast outliers (e.g. mcp runs that short-
    circuited to 0.019 s on cache hits) that pull a naive min() far
    below the realistic per-prompt baseline. We compare CURRENT runs
    against the DEFAULT-mode historical baseline so the column reads
    as "what jaeger_os used to do on the same prompt with no extras."
    """
    bests: dict[str, float] = {}
    if not HISTORY_PATH.exists():
        return bests
    with HISTORY_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("framework") != LEGACY_FRAMEWORK:
                continue
            # mode_tag is None for older entries (pre-mode-tagging) and
            # "default" for the default-mode runs we want. Anything
            # else (mcp / think / memory) is a feature-toggled run
            # whose timings aren't comparable to our plain bench.
            mode_tag = e.get("mode_tag")
            if mode_tag not in (None, "default"):
                continue
            prompt = e.get("prompt")
            total = e.get("total")
            if not prompt or not isinstance(total, (int, float)):
                continue
            current = bests.get(prompt)
            if current is None or total < current:
                bests[prompt] = float(total)
    return bests


def load_latest_run(framework: str) -> dict[str, dict[str, Any]]:
    """Return ``{prompt: latest_row}`` for the most recent run_id
    of ``framework`` in the history file. Used by --render-only."""
    if not HISTORY_PATH.exists():
        return {}
    runs: dict[str, list[dict[str, Any]]] = {}
    with HISTORY_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("framework") != framework:
                continue
            runs.setdefault(e.get("run_id") or "", []).append(e)
    if not runs:
        return {}
    latest_id = max(runs)
    return {row["prompt"]: row for row in runs[latest_id] if row.get("prompt")}


# ── markdown rendering ─────────────────────────────────────────────

def render_benchmark_md(
    prompts: list[tuple[str, str | None]],
    jaeger_rows: list[dict[str, Any]] | None,
    lilith_rows: list[dict[str, Any]] | None,
    run_id: str,
) -> None:
    """Write BENCHMARK.md with the consolidated table.

    Three columns per prompt: legacy best (lowest historical
    python_pydantic_ai total), current jaeger_os, current lilith.
    Mirrors the 5-way table format from the historical archive so
    readers familiar with that doc don't need to relearn the layout.
    """
    legacy = load_legacy_bests()
    jaeger_by_prompt: dict[str, dict[str, Any]] = {}
    lilith_by_prompt: dict[str, dict[str, Any]] = {}
    if jaeger_rows is not None:
        for r in jaeger_rows:
            jaeger_by_prompt[r["prompt"]] = r
    if lilith_rows is not None:
        for r in lilith_rows:
            lilith_by_prompt[r["prompt"]] = r

    lines: list[str] = []
    lines.append("# Jaeger-OS timing benchmark")
    lines.append("")
    lines.append(
        f"Last run: `{run_id}` · model: Gemma 4 26B-A4B Q4_K_M · "
        "transport: in-process llama-cpp-python."
    )
    lines.append("")
    lines.append(
        "All numbers are wall-clock seconds for one full prompt turn "
        "(decide → tool → optional finalize). The **legacy** column "
        "is the lowest historical total ever recorded for "
        f"`{LEGACY_FRAMEWORK}` on that prompt — jaeger_os was forked "
        f"from {LEGACY_FRAMEWORK}, so it IS the historical jaeger "
        "performance record. `—` = no historical entry for that prompt."
    )
    lines.append("")
    lines.append("Regenerate with `python benchmark/timing/bench.py` "
                 "or `--render-only` to re-render from existing history.")
    lines.append("")

    # ── Section 1: per-prompt total seconds ────────────────────────
    lines.append("## Per-prompt total seconds")
    lines.append("")
    header_cells = ["prompt", "expected tool", "legacy", "jaeger_os"]
    if lilith_rows is not None:
        header_cells.append("lilith")
    lines.append("| " + " | ".join(header_cells) + " |")
    align_cells = ["---"] * 2 + ["---:"] * (len(header_cells) - 2)
    lines.append("|" + "|".join(align_cells) + "|")

    sum_legacy = 0.0
    sum_jaeger = 0.0
    sum_lilith = 0.0
    n_legacy = n_jaeger = n_lilith = 0
    for prompt, expected in prompts:
        short = prompt if len(prompt) <= 70 else prompt[:67] + "..."
        legacy_v = legacy.get(prompt)
        jaeger_row = jaeger_by_prompt.get(prompt)
        lilith_row = lilith_by_prompt.get(prompt)
        row_cells = [
            short,
            f"`{expected}`" if expected else "_(free-text)_",
            f"{legacy_v:.2f}" if legacy_v is not None else "—",
            (
                f"{jaeger_row['elapsed_s']:.2f}"
                if jaeger_row else "—"
            ),
        ]
        if lilith_rows is not None:
            row_cells.append(
                f"{lilith_row['elapsed_s']:.2f}" if lilith_row else "—"
            )
        lines.append("| " + " | ".join(row_cells) + " |")
        if legacy_v is not None:
            sum_legacy += legacy_v
            n_legacy += 1
        if jaeger_row:
            sum_jaeger += jaeger_row["elapsed_s"]
            n_jaeger += 1
        if lilith_row:
            sum_lilith += lilith_row["elapsed_s"]
            n_lilith += 1

    totals_cells = [
        "**TOTAL**", "",
        f"**{sum_legacy:.2f}**" if n_legacy else "—",
        f"**{sum_jaeger:.2f}**" if n_jaeger else "—",
    ]
    if lilith_rows is not None:
        totals_cells.append(f"**{sum_lilith:.2f}**" if n_lilith else "—")
    lines.append("| " + " | ".join(totals_cells) + " |")
    avg_cells = [
        "**AVG / prompt**", "",
        f"**{sum_legacy / n_legacy:.2f}**" if n_legacy else "—",
        f"**{sum_jaeger / n_jaeger:.2f}**" if n_jaeger else "—",
    ]
    if lilith_rows is not None:
        avg_cells.append(
            f"**{sum_lilith / n_lilith:.2f}**" if n_lilith else "—"
        )
    lines.append("| " + " | ".join(avg_cells) + " |")
    lines.append("")

    # ── Section 2: routing accuracy + headlines ────────────────────
    lines.append("## Headlines")
    lines.append("")
    if jaeger_rows is not None:
        passed = sum(1 for r in jaeger_rows if r["match"])
        lines.append(
            f"- **jaeger_os** — {len(jaeger_rows)} prompts run; "
            f"routing OK on **{passed}/{len(jaeger_rows)}** "
            f"({100*passed/len(jaeger_rows):.0f}%); "
            f"total {sum_jaeger:.2f}s, "
            f"avg {sum_jaeger / n_jaeger:.2f}s/prompt."
        )
    if lilith_rows is not None:
        passed = sum(1 for r in lilith_rows if r["match"])
        lines.append(
            f"- **lilith** — {len(lilith_rows)} prompts run; "
            f"routing OK on **{passed}/{len(lilith_rows)}** "
            f"({100*passed/len(lilith_rows):.0f}%); "
            f"total {sum_lilith:.2f}s, "
            f"avg {sum_lilith / n_lilith:.2f}s/prompt."
        )
    if n_legacy:
        lines.append(
            f"- **legacy** ({LEGACY_FRAMEWORK}) best-of-history — "
            f"{n_legacy}/{len(prompts)} prompts covered; "
            f"total {sum_legacy:.2f}s, "
            f"avg {sum_legacy / n_legacy:.2f}s/prompt."
        )
    if jaeger_rows is not None and n_legacy and n_jaeger:
        ratio = (sum_jaeger / n_jaeger) / (sum_legacy / n_legacy)
        if ratio >= 1.0:
            lines.append(
                f"- **jaeger_os vs legacy:** "
                f"{(ratio - 1) * 100:+.0f}% slower than the historical best."
            )
        else:
            lines.append(
                f"- **jaeger_os vs legacy:** "
                f"{(1 - ratio) * 100:+.0f}% faster than the historical best."
            )
    lines.append("")

    # ── Section 3: how it was generated ────────────────────────────
    lines.append("## How this was generated")
    lines.append("")
    lines.append(f"- **History file:** `benchmark/timing/bench_history.jsonl` "
                 f"(append-only; this run's rows already landed there).")
    lines.append(f"- **Bench script:** `benchmark/timing/bench.py`.")
    lines.append(f"- **Prompt set:** {len(prompts)} prompts consolidated from "
                 "the original 5-way bench + the focused jaeger_os 7-prompt "
                 "set. See `DEFAULT_PROMPTS` in `bench.py`.")
    lines.append("- **Transport:** in-process `llama-cpp-python` for both "
                 "frameworks. Apples-to-apples on the same model in the same "
                 "process state.")
    lines.append("")

    BENCHMARK_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {BENCHMARK_MD.relative_to(PROJECT_ROOT)}", flush=True)


# ── CLI ────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", type=int, default=1,
                   help="Repeat each prompt N times.")
    p.add_argument("--prompts", type=Path, default=None,
                   help="Optional file with one prompt per line "
                        "(no expected_tool — routing accuracy skipped).")
    p.add_argument("--instance-dir", type=Path, default=None,
                   help="Use this jaeger_os instance dir instead of a temp one.")
    p.add_argument("--render-only", action="store_true",
                   help="Skip running prompts; regenerate BENCHMARK.md "
                        "from the most recent runs in bench_history.jsonl.")
    p.add_argument("--json-output", type=Path, default=None,
                   help="Write this run's rows as JSON to FILE so the "
                        "unified bench can ingest without re-running.")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.prompts:
        prompts: list[tuple[str, str | None]] = [
            (line.strip(), None)
            for line in args.prompts.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    else:
        prompts = list(DEFAULT_PROMPTS)

    if args.render_only:
        jaeger_latest = load_latest_run("jaeger_os")
        jaeger_rows = (
            [
                {"prompt": p, "elapsed_s": jaeger_latest[p]["total"],
                 "match": jaeger_latest[p].get("match", True)}
                for p, _ in prompts if p in jaeger_latest
            ]
            if jaeger_latest else None
        )
        run_id = "(render-only — see history file for source run_ids)"
        render_benchmark_md(prompts, jaeger_rows, None, run_id)
        return 0

    run_id = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Bench: {len(prompts)} prompt(s) × {args.runs} run(s) per "
          f"framework. run_id={run_id}")

    jaeger_rows: list[dict[str, Any]] | None = None

    instance_dir = args.instance_dir
    cleanup = False
    if instance_dir is None:
        tmp = Path(tempfile.mkdtemp(prefix="jaeger_bench_"))
        instance_dir = tmp / "instance"
        cleanup = True
    try:
        os.environ["JAEGER_INSTANCE_DIR"] = str(instance_dir)
        jaeger_rows = run_jaeger_os(prompts, args.runs, instance_dir)
        append_to_history(jaeger_rows, run_id)
    finally:
        if cleanup:
            import shutil
            shutil.rmtree(instance_dir.parent, ignore_errors=True)

    render_benchmark_md(prompts, jaeger_rows, None, run_id)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps({
                "run_id": run_id,
                "jaeger_rows": jaeger_rows or [],
            }, default=str, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {args.json_output}", flush=True)

    # Per-framework summary printed to stdout for the operator's
    # immediate eyeball before opening BENCHMARK.md.
    for label, rows in (("jaeger_os", jaeger_rows),):
        if not rows:
            continue
        elapsed = [r["elapsed_s"] for r in rows]
        passed = sum(1 for r in rows if r["match"])
        print(f"\n=== {label} summary ===")
        print(json.dumps({
            "turns": len(rows),
            "passed_routing": passed,
            "elapsed_total_s": round(sum(elapsed), 3),
            "elapsed_mean_s": round(statistics.fmean(elapsed), 3),
            "elapsed_median_s": round(statistics.median(elapsed), 3),
            "elapsed_min_s": round(min(elapsed), 3),
            "elapsed_max_s": round(max(elapsed), 3),
        }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
