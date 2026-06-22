#!/usr/bin/env python3
"""Model sanity sweep — hardware-health check across many GGUFs.

For each model, runs ``model_sanity_probe`` in its OWN subprocess (so
memory is fully reclaimed between models and a bad load can't poison the
rest) and collects:

  * GPU offload — ``N/M layers`` + Metal/CPU buffer split (did it fit?)
  * raw tok/s on a fixed trivial prompt (generation speed alone)
  * for hybrid thinking models, BOTH modes — reasoning ON (deep-think)
    and OFF (real-time) — since a model is used both ways

This is NOT the task benchmark (``run_model_sweep`` over the 51-case
corpus). It answers "is this model healthy + how fast is it really",
which corpus wall-clock can't separate from task verbosity.

Usage:  ``python run_model_sanity.py <models.txt>``  (one GGUF path/line)
Writes a markdown report to ``benchmark/sanity/SANITY_<ts>.md``.
Honors ``JAEGER_BENCH_MODEL_TIMEOUT`` (default 300s/model — load + 2
short gens is quick; a timeout means the model wouldn't load).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
PROBE = REPO / "benchmark" / "model_sanity_probe.py"


def _probe_one(model_path: str, timeout_s: float) -> dict:
    name = os.path.basename(model_path)[:-5]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    # macOS fork-safety (same as the corpus sweep) — avoids the xzone
    # malloc-fork SIGTRAP when we spawn the probe subprocess.
    env.setdefault("MallocNanoZone", "0")
    env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    try:
        proc = subprocess.run(
            [sys.executable, str(PROBE), model_path],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return {"model": name, "error": f"timeout (load > {timeout_s:.0f}s)"}
    for line in (proc.stdout or "").splitlines():
        if line.startswith("SANITY_JSON:"):
            try:
                return json.loads(line[len("SANITY_JSON:"):])
            except json.JSONDecodeError:
                break
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-1:] or [""]
    return {"model": name, "error": f"no result (rc={proc.returncode}): {tail[0][:80]}"}


def _render(results: list[dict]) -> str:
    lines = [
        "# Model sanity sweep — hardware health & raw speed",
        "",
        "Per-model: did it fully offload to GPU, what's its raw tok/s on a "
        "trivial prompt, and (for hybrid thinking models) how does it "
        "behave with reasoning ON (deep-think) vs OFF (real-time). "
        "Separate from task accuracy — see `HISTORY.md` for that.",
        "",
        "| Model | GB | GPU layers | Metal/CPU MB | Load s | Mode | tok/s | "
        "gen tok | wall s | thinks |",
        "|---|---:|---|---|---:|---|---:|---:|---:|:--:|",
    ]
    for r in results:
        if r.get("error"):
            lines.append(
                f"| `{r['model']}` | — | — | — | — | **ERROR** | — | — | — | "
                f"{r['error']} |")
            continue
        gl = r.get("gpu_layers", "?")
        full = r.get("full_offload")
        gl_disp = f"{gl}" + ("" if full else " ⚠️PARTIAL" if full is False else "")
        buf = f"{r.get('metal_mb', 0)}/{r.get('cpu_mb', 0)}"
        runs = r.get("runs") or [{}]
        for i, run in enumerate(runs):
            head = (f"| `{r['model']}` | {r.get('size_gb','?')} | {gl_disp} | "
                    f"{buf} | {r.get('load_s','?')} " if i == 0
                    else "|  |  |  |  |  ")
            thinks = "yes" if run.get("thinks") else "no"
            lines.append(
                f"{head}| {run.get('mode','?')} | {run.get('tps',0)} | "
                f"{run.get('gen_tokens',0)} | {run.get('wall_s',0)} | {thinks} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_model_sanity.py <models.txt>", file=sys.stderr)
        return 2
    paths = [ln.strip() for ln in open(sys.argv[1]) if ln.strip()]
    try:
        timeout_s = float(os.environ.get("JAEGER_BENCH_MODEL_TIMEOUT", "") or 300)
    except ValueError:
        timeout_s = 300.0
    print(f"Sanity-probing {len(paths)} model(s) — {timeout_s:.0f}s/model cap\n",
          flush=True)
    out_dir = REPO / "benchmark" / "sanity"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    report = out_dir / f"SANITY_{ts}.md"
    raw = out_dir / f"SANITY_{ts}.jsonl"

    results: list[dict] = []
    for p in paths:
        name = os.path.basename(p)[:-5]
        print(f"── {name} ...", flush=True)
        res = _probe_one(p, timeout_s)
        results.append(res)
        if res.get("error"):
            print(f"   ERROR: {res['error']}", flush=True)
        else:
            off = res.get("gpu_layers", "?")
            for run in res.get("runs", []):
                print(f"   [{run.get('mode')}] {run.get('tps')} tok/s, "
                      f"{run.get('gen_tokens')} tok, {run.get('wall_s')}s "
                      f"(thinks={run.get('thinks')})  | offload {off}",
                      flush=True)
        # Write INCREMENTALLY after every model — a crash / panic / kill
        # mid-sweep then keeps everything probed so far instead of losing
        # the whole run (the report used to write only at the end).
        report.write_text(_render(results), encoding="utf-8")
        raw.write_text("\n".join(json.dumps(r) for r in results) + "\n",
                       encoding="utf-8")

    print(f"\nReport: {report.relative_to(REPO)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
