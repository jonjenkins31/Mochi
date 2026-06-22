#!/usr/bin/env python3
"""Bench every local model in turn, write a comparison table.

Usage::

    python benchmark/run_model_sweep.py /tmp/bench_models.txt
    python benchmark/run_model_sweep.py /tmp/bench_models.txt --level 1

The input file lists one absolute model path per line. For each entry
we:

  1. Edit the active instance's ``config.yaml`` so ``model.model_path``
     points at that file (preserving everything else).
  2. Spawn ``run_level.py`` as a fresh subprocess — each model gets a
     clean Python interpreter so module-level state doesn't leak, the
     drift parser is the latest committed code, and a crash on one
     model doesn't poison the others.
  3. Parse the per-row output and the BENCHMARK_levelN.md summary the
     run dropped for us.
  4. Restore the original config at the end (always, via try/finally).

Results land in ``dev/benchmark/sweep/RESULTS_<timestamp>.md`` plus a
``sweep_rows.jsonl`` with per-model totals so a future script can plot
trends.  (Was ``benchmark/sweep/`` until 0.3.0 fixed the aggregator
mismatch — see ``jaeger_os/daemon/bench_history_verb.py``.)

The driver is deliberately dumb — it doesn't try to be clever about
parallelism or hot-swapping. Each model loads from cold; one process at
a time. That's fine for an overnight comparison and far easier to
debug than a hot-swap dance that could leak GPU memory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict


REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"


def _resolve_active_config_path() -> pathlib.Path:
    """Locate the config.yaml the bench subprocess will actually load.

    INST-10 (0.2.0) moved per-instance state out of the bundled
    ``src/jaeger_os/instance/default/`` directory and into
    ``~/.jaeger/instances/<name>/``. The old hard-coded path in this
    script (``DEFAULT_INSTANCE_CFG``) edited the WRONG file after the
    move — the sweep's config-swap silently no-op'd and every model
    ran against whatever the live instance's config already pointed
    at (so e.g. a 3-model compare actually benched the same model 3×
    and showed only statistical noise as the "difference").

    Resolution order (matches ``core/instance/instance.py:resolve_instance_dir``):

      1. ``JAEGER_INSTANCE_DIR`` env var — explicit path. Used for
         the dev sandbox (``sandbox/jros-dev/``) and for one-off
         runs against a non-default instance.
      2. ``~/.jaeger/instances/<JAEGER_INSTANCE_NAME or 'default'>/``.
      3. Fall back to the legacy bundled-skeleton path so the script
         still works on a pre-INST-10 checkout if anyone digs one up.
    """
    env_dir = os.environ.get("JAEGER_INSTANCE_DIR")
    if env_dir:
        return pathlib.Path(env_dir).expanduser() / "config.yaml"
    name = os.environ.get("JAEGER_INSTANCE_NAME") or "default"
    home_cfg = pathlib.Path.home() / ".jaeger" / "instances" / name / "config.yaml"
    if home_cfg.exists():
        return home_cfg
    return REPO / "src" / "jaeger_os" / "instance" / "default" / "config.yaml"


# Resolved once at module load — the subprocess inherits this script's
# env, so the path it reads from is the same one we edit here.
DEFAULT_INSTANCE_CFG = _resolve_active_config_path()
SWEEP_DIR = REPO / "dev/benchmark" / "sweep"


@dataclass
class ModelResult:
    name: str
    path: str
    size_gb: float
    level: int
    cases: int = 0
    route_ok: int = 0
    answer_ok: int = 0
    elapsed_s: float = 0.0
    load_s: float = 0.0
    p50_turn_s: float = 0.0
    p95_turn_s: float = 0.0
    avg_turn_s: float = 0.0
    # Tokens-per-second — real tokenizer count from the adapter's
    # ``usage`` field when reported, whitespace-split estimate
    # otherwise. ``tokens_source`` carries which one it is so the
    # comparison table can label the column honestly.
    tokens_per_sec: float = 0.0
    tokens_source: str = "n/a"
    failures: list[str] = field(default_factory=list)
    return_code: int = -1
    error: str | None = None

    @property
    def route_pct(self) -> float:
        return (self.route_ok / self.cases * 100) if self.cases else 0.0

    @property
    def answer_pct(self) -> float:
        return (self.answer_ok / self.cases * 100) if self.cases else 0.0


# ── config swap ────────────────────────────────────────────────────


def _read_config_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _backend_for_path(model_path: str) -> str:
    """Derive the backend from the model path: a ``.gguf`` *file* loads via
    ``llama_cpp_python``; an MLX model *directory* (config.json + safetensors)
    loads via ``mlx_lm``. Lets one models-file mix GGUF and MLX entries."""
    if os.path.isdir(model_path) or not model_path.endswith(".gguf"):
        return "mlx_lm"
    return "llama_cpp_python"


def _write_model_path(text: str, new_model_path: str) -> str:
    """Replace ``model.model_path`` (and ``model.backend``), preserving rest.

    Earlier versions used a regex-replace on ``model_path:`` — that
    broke when the bench subprocess re-wrote config.yaml during boot
    (normalised key order, added defaults, etc.) so the regex no
    longer matched after the first iteration. YAML round-trip is the
    robust answer: parse → mutate one key → emit.

    We use ``ruamel.yaml`` if available for comment preservation, then
    fall back to stdlib ``yaml`` (loses comments) and finally to the
    regex path as a last resort. Comments only matter for human
    readability of intermediate states; functionally the bench just
    needs ``model.model_path`` to be the path we asked for.

    The ``backend`` is derived from the path (GGUF file vs MLX directory) so
    a single sweep can cover both engines."""
    backend = _backend_for_path(new_model_path)
    try:
        from ruamel.yaml import YAML
        import io
        yaml = YAML()
        yaml.preserve_quotes = True
        data = yaml.load(text)
        if "model" in data and isinstance(data["model"], dict):
            data["model"]["model_path"] = new_model_path
            data["model"]["backend"] = backend
            buf = io.StringIO()
            yaml.dump(data, buf)
            return buf.getvalue()
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 — fall back to next strategy
        pass

    try:
        import yaml as _yaml
        data = _yaml.safe_load(text)
        if isinstance(data, dict) and isinstance(data.get("model"), dict):
            data["model"]["model_path"] = new_model_path
            data["model"]["backend"] = backend
            return _yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    except Exception:  # noqa: BLE001
        pass

    # Last resort — regex. Same as the original implementation.
    pattern = re.compile(r"^(\s*model_path:\s*).+$", re.MULTILINE)
    new = pattern.sub(rf"\g<1>{new_model_path}", text, count=1)
    if new == text:
        raise RuntimeError(
            "model_path: line not found in config.yaml and no YAML "
            "library available — install ``pyyaml`` or ``ruamel.yaml``."
        )
    return new


# ── run one model ──────────────────────────────────────────────────


_HYBRID_FAMILY_TOKENS = ("qwen3", "gemma-4", "gemma4")
# Names that LOOK like the hybrid families but aren't (the sanity sweep
# verified these emit no ``enable_thinking`` toggle in their template):
#   * ``deepseek`` — DeepSeek-R1 is *distilled from* Qwen3 but always
#     reasons; no toggle.
#   * ``coder`` — Qwen3-Coder is a coder fine-tune; no toggle.
#   * ``reasoning`` / ``deephermes`` — explicit always-reasoning models.
_HYBRID_FALSE_POSITIVES = ("deepseek", "coder", "reasoning", "deephermes")


def _is_hybrid_by_name(stem: str) -> bool:
    """Best-effort 'is this a hybrid thinking model' check from the
    filename stem. Qwen3.x and gemma-4 expose ``enable_thinking`` in
    their chat templates; everything else doesn't. Used to decide
    whether the sweep runs one mode (default) or two (think + direct).
    If the heuristic gets it wrong (declares hybrid when not), the
    runtime check in :class:`LocalLlamaAdapter` makes the toggle a
    no-op anyway — worst case is a duplicated subprocess, never a
    behaviour change."""
    low = stem.lower()
    if any(bad in low for bad in _HYBRID_FALSE_POSITIVES):
        return False
    return any(tok in low for tok in _HYBRID_FAMILY_TOKENS)


def _human_name(path: str) -> str:
    """Short label for the report — last component minus the .gguf."""
    return pathlib.Path(path).stem


def _file_size_gb(path: str) -> float:
    try:
        p = pathlib.Path(path)
        if p.is_dir():
            # MLX model: sum the weight shards / config in the directory.
            return sum(
                f.stat().st_size for f in p.rglob("*") if f.is_file()
            ) / 1e9
        return p.stat().st_size / 1e9
    except OSError:
        return 0.0


# Flat-bench per-row regex. The flat bench prints
# ``[ROW <idx>] <case_id>   pass=✓|✗  <elapsed>s`` for every case; the
# levels concept was retired in 0.1.1 when the bench got flattened into
# a single corpus. Per-tag drill-downs come from the JSON summary the
# subprocess writes alongside, not the console output.
_ROW_RE_FLAT = re.compile(
    r"\[ROW (?P<idx>\d+)\][^\n]*?pass=(?P<pass_mark>[✓✗])\s+(?P<elapsed>[\d.]+)s",
)


def _parse_bench_output(stdout: str) -> tuple[int, int, int, list[float], list[str], float]:
    """Walk the per-row console output and pull totals + per-row latencies.

    The flat bench prints one ``[ROW <idx>]`` line per case with a
    ``pass=✓|✗`` and a wall-time. The composite per-case verdict already
    rolls up routing + answer-check + no-hallucination; we don't need
    to disaggregate them here. (Detailed breakdown is in the JSON
    summary the subprocess wrote next to its rows.jsonl.)

    Returns (cases, pass_count, answer_ok, latencies, failed_rows, load_s).
    ``answer_ok`` is reported as equal to ``pass_count`` because the
    flat bench's pass marker already encodes the answer-check outcome —
    keeping the tuple shape stable so existing report-rendering code
    doesn't need to change.
    """
    cases = 0
    pass_count = 0
    latencies: list[float] = []
    failures: list[str] = []
    load_s = 0.0
    for raw in stdout.splitlines():
        if "loaded in " in raw and load_s == 0.0:
            try:
                load_s = float(re.search(r"loaded in (\S+)s", raw).group(1))
            except (AttributeError, ValueError):
                pass
        m = _ROW_RE_FLAT.search(raw)
        if not m:
            continue
        cases += 1
        passed = m.group("pass_mark") == "✓"
        if passed:
            pass_count += 1
        latencies.append(float(m.group("elapsed")))
        if not passed:
            # Failure label = the case id (it lives between the bracket
            # and the ``pass=`` field in the row format).
            mid = raw.split("] ", 1)[1] if "] " in raw else raw
            label = mid.split("pass=", 1)[0].strip()
            failures.append(label[:60])
    return cases, pass_count, pass_count, latencies, failures, load_s


def run_one(model_path: str, *, level: int) -> ModelResult:
    name = _human_name(model_path)
    size = _file_size_gb(model_path)
    print(f"\n══════════════ {name}  ({size:.1f} GB) ══════════════", flush=True)

    saved = _read_config_text(DEFAULT_INSTANCE_CFG)
    try:
        DEFAULT_INSTANCE_CFG.write_text(
            _write_model_path(saved, model_path), encoding="utf-8",
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = (str(SRC) + os.pathsep + env.get("PYTHONPATH", ""))
        # macOS fork-safety — see bench_compare_verb for the full why.
        # On macOS 26's xzone allocator, fork()ing this bench
        # subprocess after the sweep driver imported numpy/jaeger
        # crashes the child in ``_malloc_fork_child``. Force the
        # legacy allocator + disable the Obj-C fork guard so the
        # spawn survives. Redundant with the parent setting it, but
        # safe to assert here too (covers a direct
        # ``python run_model_sweep.py`` invocation that didn't go
        # through ``jaeger bench compare``).
        env.setdefault("MallocNanoZone", "0")
        env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
        # Per-run HISTORY.md regeneration is INTENTIONALLY enabled
        # inside each model's subprocess. A multi-model sweep over 11
        # GGUFs can take 6+ hours; updating the leaderboard only at the
        # end means an interrupted sweep loses partial-progress
        # visibility. Per-run regeneration is cheap (<1s for the
        # current data volume) and lets the user open HISTORY.md
        # mid-sweep to see scores landing as they finish — and to see
        # uninstalled-model rows disappear as soon as they're deleted
        # from disk during the sweep.
        # Forward ``--tags`` / ``--limit`` from the env when the caller
        # (``jaeger bench compare``) set them. Lets the operator narrow
        # the sweep to e.g. routing-only without re-running 51 cases
        # per model.
        extra_args: list[str] = []
        _tags = env.get("JAEGER_BENCH_TAGS", "").strip()
        if _tags:
            extra_args.extend(["--tags", _tags])
        _limit = env.get("JAEGER_BENCH_LIMIT", "").strip()
        if _limit and _limit != "0":
            extra_args.extend(["--limit", _limit])
        started = time.perf_counter()
        # Per-model wall-clock cap. This is a **wedged-process backstop**,
        # NOT a fairness/comparability gate. The real "is this model
        # broken" signal is the per-case stall watchdog
        # (``JAEGER_BENCH_STALL_S``, default 45s) — that's what flags
        # actually-stuck decodes. The model-level cap only exists so a
        # truly hung llama-cpp process doesn't run forever and never
        # release the queue. Default 2 hours: covers 59 cases × 60s
        # worst-case (~60 min) plus generous headroom for big MoEs in
        # think mode. Overridable via ``JAEGER_BENCH_MODEL_TIMEOUT``
        # (seconds). Do NOT lower this to "speed up the sweep" — a
        # capable-but-slow model getting cut off mid-corpus produces
        # no result and looks identical to a broken model in the log,
        # which is exactly the comparison we DON'T want to make.
        try:
            _model_timeout = float(os.environ.get(
                "JAEGER_BENCH_MODEL_TIMEOUT", "") or 7200)
        except ValueError:
            _model_timeout = 7200.0
        proc = subprocess.run(
            [sys.executable, str(REPO / "dev/benchmark" / "run_flat_bench.py"),
             "--no-warmup", *extra_args],
            cwd=str(REPO),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_model_timeout,
        )
        wall = time.perf_counter() - started
    except subprocess.TimeoutExpired as exc:
        return ModelResult(
            name=name, path=model_path, size_gb=size, level=level,
            error=f"timeout after {exc.timeout:.0f}s", return_code=-1,
        )
    except Exception as exc:  # noqa: BLE001 — surface every failure mode
        return ModelResult(
            name=name, path=model_path, size_gb=size, level=level,
            error=f"{type(exc).__name__}: {exc}", return_code=-1,
        )
    finally:
        DEFAULT_INSTANCE_CFG.write_text(saved, encoding="utf-8")

    cases, route_ok, ans_ok, lats, fails, load_s = _parse_bench_output(proc.stdout)
    lats.sort()
    p50 = lats[len(lats) // 2] if lats else 0.0
    p95_idx = max(0, int(round(0.95 * (len(lats) - 1)))) if lats else 0
    p95 = lats[p95_idx] if lats else 0.0
    avg = (sum(lats) / len(lats)) if lats else 0.0

    # Tokens-per-second + tokens_source come from the per-subprocess
    # summary the inner ``run_flat_bench.py`` writes into
    # ``benchmark/flat/<model>/<ts>/``. Find the newest run dir for
    # THIS model, then look for the summary file — the filename
    # convention changed 2026-05-27 from ``summary.json`` to
    # ``<model>-<ts>-summary.json``; try both so a sweep run mid-
    # transition still finds it.
    tps = 0.0
    tps_source = "n/a"
    try:
        flat_root = REPO / "dev/benchmark" / "flat" / name
        if flat_root.is_dir():
            run_dirs = sorted(
                (d for d in flat_root.iterdir() if d.is_dir()),
                key=lambda d: d.name, reverse=True,
            )
            if run_dirs:
                run_dir = run_dirs[0]
                # New naming: <model>-<ts>-summary.json
                candidates = list(run_dir.glob("*-summary.json"))
                summary_path = candidates[0] if candidates else (
                    run_dir / "summary.json"  # legacy fallback
                )
                if summary_path.exists():
                    s = json.loads(summary_path.read_text(encoding="utf-8"))
                    m = s.get("metrics") or {}
                    tps = float(m.get("answer_tokens_per_sec", 0.0) or 0.0)
                    tps_source = m.get(
                        "answer_tokens_source", "whitespace_estimate"
                    )
    except Exception:  # noqa: BLE001 — TPS is metadata; never fail the row
        pass

    result = ModelResult(
        name=name,
        path=model_path,
        size_gb=size,
        level=level,
        cases=cases,
        route_ok=route_ok,
        answer_ok=ans_ok,
        elapsed_s=wall,
        load_s=load_s,
        p50_turn_s=p50,
        p95_turn_s=p95,
        avg_turn_s=avg,
        tokens_per_sec=tps,
        tokens_source=tps_source,
        failures=fails,
        return_code=proc.returncode,
    )
    # Tail of the subprocess output to a per-model log so it's easy to
    # poke at failures after the fact without redoing the run.
    log_path = SWEEP_DIR / f"{name}.stdout.log"
    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    log_path.write_text(proc.stdout, encoding="utf-8")
    print(
        f"  → route {result.route_ok:>2}/{result.cases:>2} "
        f"({result.route_pct:.1f}%)  "
        f"answer {result.answer_ok:>2}/{result.cases:>2} "
        f"({result.answer_pct:.1f}%)  "
        f"p50 {result.p50_turn_s:.1f}s  "
        f"tps {result.tokens_per_sec:.1f}  "
        f"total {result.elapsed_s:.0f}s",
        flush=True,
    )
    return result


# ── report ─────────────────────────────────────────────────────────


def _write_report(results: list[ModelResult], *, level: int, out_dir: pathlib.Path) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = out_dir / f"RESULTS_{ts}_level{level}.md"

    # Rank by routing %, tiebreak by p50 latency.
    ranked = sorted(
        [r for r in results if r.cases > 0],
        key=lambda r: (-r.route_pct, r.p50_turn_s),
    )

    lines: list[str] = [
        f"# Model sweep — Level {level}",
        "",
        f"Run at {ts}.  Each model loaded cold, benched against the same "
        f"{ranked[0].cases if ranked else '?'}-prompt Level-{level} suite, "
        "then unloaded.",
        "",
        "Routing % is the primary signal — "
        "answer % is auxiliary (many bench prompts have no expected "
        "answer string, so a '—' in the per-row output is neither pass "
        "nor fail there).",
        "",
        "## Ranking (routing% desc, p50 latency asc)",
        "",
        "TPS = output tokens-per-second sustained across the corpus. "
        "Real tokenizer counts when the adapter reports ``usage`` "
        "(local llama-cpp, OpenAI, Anthropic); whitespace-split estimate "
        "otherwise — see the `tokens_source` column.",
        "",
        "| # | Model | Size GB | Route % | Answer % | p50 s | p95 s | "
        "TPS | tokens_source | Load s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ranked, 1):
        lines.append(
            f"| {i} | `{r.name}` | {r.size_gb:.1f} | "
            f"{r.route_pct:.1f}% ({r.route_ok}/{r.cases}) | "
            f"{r.answer_pct:.1f}% ({r.answer_ok}/{r.cases}) | "
            f"{r.p50_turn_s:.1f} | {r.p95_turn_s:.1f} | "
            f"{r.tokens_per_sec:.1f} | {r.tokens_source} | "
            f"{r.load_s:.1f} |"
        )

    errored = [r for r in results if r.cases == 0]
    if errored:
        lines += [
            "",
            "## Did not produce results",
            "",
            "| Model | Error |",
            "|---|---|",
        ]
        for r in errored:
            lines.append(f"| `{r.name}` | {r.error or 'no rows parsed'} |")

    # Per-model failure surface — the FIRST 5 misrouted prompts per model.
    lines += ["", "## Where each model lost routing points", ""]
    for r in ranked:
        if not r.failures:
            continue
        lines.append(f"**`{r.name}`** — {len(r.failures)} miss(es):")
        for f in r.failures[:5]:
            lines.append(f"  • {f}")
        if len(r.failures) > 5:
            lines.append(f"  • … and {len(r.failures) - 5} more (see `sweep/{r.name}.stdout.log`)")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {md_path.relative_to(REPO)}", flush=True)
    return md_path


def _write_jsonl(results: list[ModelResult], *, out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "sweep_rows.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps({**asdict(r),
                                 "ts": dt.datetime.now().isoformat()}) + "\n")


# ── entry ──────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("models_file",
                    help="Text file with one absolute model path per line.")
    # ``--level`` is retained as a no-op for backwards compatibility
    # with callers that still pass it; the bench is one flat corpus
    # now and the value is ignored at the row level. Use the flat-bench
    # subprocess's ``--tags`` flag instead if you want a subset.
    ap.add_argument("--level", type=int, default=0,
                    help="Deprecated — kept for backwards compat. The "
                         "bench is now a single flat corpus.")
    args = ap.parse_args()

    with open(args.models_file, "r", encoding="utf-8") as fh:
        paths = [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    paths = [p for p in paths if pathlib.Path(p).exists()]
    if not paths:
        print("No model paths found in the list (or none exist on disk).",
              file=sys.stderr)
        return 2

    # Methodology: the corpus benchmark measures IDEAL-STATE behaviour
    # — every model runs once in the mode it would actually be
    # deployed in (``auto`` for toggle-capable, the model's only mode
    # for ``always``/``never`` lineages). The default with NO env set
    # is therefore ``auto`` for every path — no hybrid auto-pairing.
    #
    # Forced ``on`` / ``off`` runs are SANITY-PROBE comparison data,
    # not corpus rank entries — they only show up if the operator
    # explicitly sets ``JAEGER_BENCH_THINKING=on`` (or ``off``) for a
    # specific research-comparison sweep. The leaderboard renderer
    # filters non-ideal rows out of the main per-model table.
    forced_mode = (os.environ.get("JAEGER_BENCH_THINKING") or "").strip().lower()
    _FORCED_MODES = ("on", "off", "auto", "manual",
                     "true", "false", "1", "0")
    chosen_mode = forced_mode if forced_mode in _FORCED_MODES else "auto"
    plan: list[tuple[str, str]] = [(p, chosen_mode) for p in paths]

    n_models = len({p for p, _ in plan})
    print(f"Sweeping {n_models} model(s) → {len(plan)} run(s) over the "
          f"flat bench corpus (mode={chosen_mode} for every model — "
          f"ideal-state methodology)",
          flush=True)
    results: list[ModelResult] = []
    for p, mode in plan:
        # Set the per-run env for this subprocess only — JAEGER_BENCH_THINKING
        # is read by run_flat_bench's adapter wiring + stamped into the
        # summary so the leaderboard groups by (model, mode).
        if mode == "auto":
            os.environ.pop("JAEGER_BENCH_THINKING", None)
        else:
            os.environ["JAEGER_BENCH_THINKING"] = mode
        results.append(run_one(p, level=args.level))
        # Write incremental progress so a crash mid-sweep doesn't lose
        # the partial results.
        _write_jsonl([results[-1]], out_dir=SWEEP_DIR)
    os.environ.pop("JAEGER_BENCH_THINKING", None)

    _write_report(results, level=args.level, out_dir=SWEEP_DIR)

    # Auto-refresh the rolling leaderboard once, now that every model's
    # summary.json is on disk. Per-model subprocesses skipped this
    # (JAEGER_SUPPRESS_HISTORY=1) so it fires exactly once per sweep.
    try:
        sys.path.insert(0, str(SRC))
        from jaeger_os.cli.verbs.bench_history_verb import write_history_md
        written = write_history_md(REPO)
        if written:
            print(f"Updated {written}", flush=True)
    except Exception:  # noqa: BLE001 — never fail a sweep over bookkeeping
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
