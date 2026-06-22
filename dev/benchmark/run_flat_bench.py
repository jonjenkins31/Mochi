#!/usr/bin/env python3
"""Boot the jaeger pipeline, run the flat self-benchmark, print rows.

Subprocess entry point for ``run_model_sweep.py`` — each model gets a
clean Python interpreter so a crash on one doesn't poison the
others. Prints one ``[ROW <idx>]`` line per case with a stable shape
that the sweep driver greps for case totals + per-row latency.

The bench itself lives in :mod:`jaeger_os.core.bench`; that's the
same code path the live agent invokes via the ``run_benchmark`` tool.
This script is the offline counterpart — one boot, full corpus, no
agent layer in front.

Usage::

    python benchmark/run_flat_bench.py              # full corpus
    python benchmark/run_flat_bench.py --tags routing
    python benchmark/run_flat_bench.py --limit 5    # smoke
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time


_REPO = pathlib.Path(__file__).resolve().parent.parent
for _candidate in (_REPO, _REPO / "src"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
os.chdir(_REPO)


def _canonical_model_name(model_path: object) -> str:
    """Return the stable benchmark model id for ``model_path``."""
    stem = pathlib.Path(str(model_path)).stem
    try:
        from jaeger_os.core.models.model_resolver import MODEL_REGISTRY
        filename = pathlib.Path(str(model_path)).name.lower()
        for key, info in MODEL_REGISTRY.items():
            if str(info.get("hf_file", "")).lower() == filename:
                return key
    except Exception:  # noqa: BLE001 — benchmark metadata only
        pass
    return stem.lower().replace("_", "-")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-warmup", action="store_true",
                   help="Skip the llama-cpp prewarm pass")
    p.add_argument("--tags", type=str, default="",
                   help="Comma-separated tag filter (routing, multistep, "
                        "multiturn, recovery, memory, files, web, code, "
                        "audio, schedule). Empty = full corpus.")
    p.add_argument("--ids", type=str, default="",
                   help="Comma-separated case ids — re-run specific cases.")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap number of cases (after filtering). 0 = none.")
    p.add_argument("--hermetic", dest="hermetic", action="store_true",
                   default=True,
                   help="Snapshot+restore mutable memory files around the "
                        "run (default). Pollution-free.")
    p.add_argument("--no-hermetic", dest="hermetic", action="store_false",
                   help="Let bench writes persist (legacy behaviour).")
    args = p.parse_args()

    print("=== Booting jaeger pipeline ===", flush=True)
    boot_started = time.perf_counter()
    from jaeger_os.main import boot_for_tui
    boot = boot_for_tui(
        instance_name="default", with_memory=True, warmup=not args.no_warmup,
    )
    load_s = time.perf_counter() - boot_started
    print(f"[boot] loaded in {load_s:.2f}s", flush=True)

    from jaeger_os.core.bench import run_bench, summarise

    tag_list = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    id_list = [i.strip() for i in (args.ids or "").split(",") if i.strip()]
    cap = args.limit if args.limit and args.limit > 0 else None

    def _on_row(idx: int, total: int, case_id: str,
                passed: bool, elapsed_s: float) -> None:
        # Stable one-line-per-row format. ``run_model_sweep.py`` greps
        # this; tag-along output (errors, etc.) goes to stderr or stays
        # inside the result dict so it doesn't break parsing.
        mark = "✓" if passed else "✗"
        print(f"  [ROW {idx:02d}] {case_id:40s} pass={mark}  "
              f"{elapsed_s:5.2f}s", flush=True)

    # System-load sampler: poll ``os.getloadavg()`` every 5s during
    # the run, stash the peak in the summary. Tells the reader how
    # hard this model strained the host while benching — orthogonal
    # to wall time (a 4-min model that pegs CPU at 50 vs a 60-min
    # model that idles at 5 is information the leaderboard couldn't
    # see before). Daemon thread so a bench crash never blocks exit.
    #
    # TODO(future): subtract a baseline. ``os.getloadavg()`` is a
    # DECAYING 1-min average, so the first sample after the bench
    # starts captures whatever load was already on the system —
    # e.g. a previous sanity sweep cooling down, or a Spotlight
    # reindex. The fix is to sample a baseline BEFORE the run starts
    # and store ``peak - baseline`` as the bench's contribution. For
    # now the absolute value is informative but the first model in a
    # back-to-back queue can show a spuriously high reading; rerun it
    # standalone for a clean number.
    import threading
    peak_load_holder = {"v": 0.0}
    _stop = threading.Event()
    def _sample_load():
        while not _stop.is_set():
            try:
                cur = os.getloadavg()[0]   # 1-min average
                if cur > peak_load_holder["v"]:
                    peak_load_holder["v"] = cur
            except OSError:
                pass
            _stop.wait(5.0)
    _sampler = threading.Thread(target=_sample_load, daemon=True)
    _sampler.start()

    started = time.perf_counter()
    try:
        rows = run_bench(boot.client, tags=tag_list or None,
                         ids=id_list or None, limit=cap, progress=_on_row,
                         hermetic=args.hermetic)
    finally:
        try:
            boot.cleanup()
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass
        _stop.set()
    wall = time.perf_counter() - started

    summary = summarise(rows)
    summary["wall_s"] = round(wall, 2)
    summary["load_s"] = round(load_s, 2)
    summary["peak_load"] = round(peak_load_holder["v"], 2)

    # Stamp the model identity into the summary so the history
    # aggregator (``jaeger bench history``) can attribute results to
    # the model that produced them — without this, multi-model sweeps
    # leave a pile of timestamped directories with no model context.
    model_name = "unknown"
    try:
        from jaeger_os.main import _pipeline as _pl
        _cfg = _pl.get("config")
        _mp = getattr(getattr(_cfg, "model", None), "model_path", None)
        if _mp:
            summary["model_path"] = str(_mp)
            model_name = _canonical_model_name(_mp)
            summary["model_name"] = model_name
    except Exception:  # noqa: BLE001 — model identity is metadata; never block
        pass
    ts = time.strftime("%Y%m%d-%H%M%S")
    summary["run_id"] = ts
    # Record which thinking mode the model ran in (Phase 2 of the cloud-
    # style ``thinking`` toggle). The leaderboard groups runs by
    # (model, thinking_mode) so a hybrid model's think-vs-direct
    # tradeoff is visible side-by-side. ``auto`` = the model's default
    # mode (unchanged behaviour, matches all historical runs).
    summary["thinking_mode"] = (
        os.environ.get("JAEGER_BENCH_THINKING") or "auto"
    ).strip().lower() or "auto"
    # Stamp the corpus version (cases.BENCHMARK_VERSION). The
    # leaderboard filters to runs of the current version so a 1.0
    # (51-case) run isn't visually ranked against a 1.1 (59-case)
    # run. Legacy summaries without this field get their version
    # inferred from total case count in the aggregator.
    try:
        from jaeger_os.core.bench.cases import BENCHMARK_VERSION
        summary["benchmark_version"] = BENCHMARK_VERSION
    except Exception:  # noqa: BLE001 — metadata, never block a bench
        pass

    # Per-model nesting under dev/benchmark/flat/<model>/<ts>/. Each
    # artifact ALSO carries ``<model>-<ts>`` in its filename — so a
    # file copied / shared out of context still self-identifies. The
    # generic ``rows.jsonl`` / ``summary.json`` names of the original
    # layout were undescriptive once moved; the prefix fixes that.
    # ``unknown`` collects runs where the config didn't expose a
    # model_path (rare; usually a misconfigured boot).
    #
    # 0.3.0: was ``benchmark/flat/<model>/<ts>/`` until
    # ``jaeger_os.cli.verbs.bench_history_verb`` (the aggregator that
    # builds ``dev/benchmark/HISTORY.md``) was found to read from
    # ``dev/benchmark/flat/`` while writers landed under
    # ``benchmark/flat/``.  Writers now match the reader so every
    # bench surfaces on the leaderboard automatically.
    out_dir = _REPO / "dev/benchmark" / "flat" / model_name / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{model_name}-{ts}"
    rows_path = out_dir / f"{prefix}-rows.jsonl"
    summary_path = out_dir / f"{prefix}-summary.json"
    log_path = out_dir / f"{prefix}.log"

    rows_path.write_text(
        "\n".join(json.dumps(r, default=str, ensure_ascii=False)
                  for r in summary["rows"]) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps({k: v for k, v in summary.items() if k != "rows"},
                   indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )

    # Human-readable per-case digest. The JSON files are for the
    # history aggregator + machine consumers; this one is for a
    # human eyeballing the run after the fact ("which case failed?",
    # "how slow was speak_file?") without `jq`-ing into JSON. Mirrors
    # what the per-row console output showed but persisted to disk.
    log_lines: list[str] = [
        f"# {model_name} — flat bench  ({ts})",
        f"# wall={wall:.1f}s  load={load_s:.1f}s  cases={summary['total']}",
        f"# passed={summary['passed']}  errors={summary['errors']}",
        "",
    ]
    metrics = summary.get("metrics") or {}
    if metrics:
        log_lines.append(
            f"# avg={metrics.get('avg_latency_s', 0):.2f}s  "
            f"p50={metrics.get('p50_latency_s', 0):.2f}s  "
            f"p95={metrics.get('p95_latency_s', 0):.2f}s  "
            f"tok/s={metrics.get('answer_tokens_per_sec', 0):.1f} "
            f"({metrics.get('answer_tokens_source', '?')})"
        )
        log_lines.append("")
    for i, r in enumerate(summary.get("rows") or []):
        mark = "✓" if r.get("case_pass") else "✗"
        log_lines.append(
            f"  [ROW {i:02}] {r.get('id', '?'):<40} pass={mark}  "
            f"{r.get('elapsed_s', 0):.2f}s"
        )
    log_lines.append("")
    log_lines.append(
        f"{summary['passed']}/{summary['total']} passed; "
        f"errors={summary['errors']}; wall={wall:.1f}s"
    )
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    total = summary["total"] or 1
    print(f"\n{summary['passed']}/{summary['total']} passed "
          f"({100 * summary['passed'] / total:.0f}%); "
          f"errors={summary['errors']}; wall={wall:.1f}s", flush=True)
    print(f"Wrote {out_dir}", flush=True)

    # Auto-refresh the rolling leaderboard so HISTORY.md is always
    # current after a bench — no manual ``jaeger bench history --write``.
    # Suppressed when running as a sweep subprocess (the sweep
    # regenerates ONCE at the end instead of 15× — one per model):
    # ``run_model_sweep.py`` sets ``JAEGER_SUPPRESS_HISTORY=1``.
    if not os.environ.get("JAEGER_SUPPRESS_HISTORY"):
        try:
            from jaeger_os.cli.verbs.bench_history_verb import write_history_md
            written = write_history_md()
            if written:
                print(f"Updated {written}", flush=True)
        except Exception:  # noqa: BLE001 — never fail a bench over bookkeeping
            pass
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
