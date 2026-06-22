#!/usr/bin/env python3
"""Direct MLX probe — does JROS's MLX path actually work post-threading-fix?

The only MLX gemma bench on record (2026-06-18 07:05) scored 0/65 — the
empty-generation signature of the MLX thread-affinity bug, and it predates
the fix in ``mlx_client.py`` (08:03) by ~1h. The model files themselves are
fine (they run in LM Studio). This script answers the narrow question the
bench can't anymore without a 20-min sweep: with the fix in place, does

  MlxClient (load on the executor thread)
    → MLXAdapter (generation on the SAME thread)
    → format_messages → call → extract_tool_calls

produce non-empty generations AND correct tool routing?

Run:  python dev/benchmark/mlx_direct_probe.py
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field

from jaeger_os.agent.adapters.mlx import MLXAdapter
from jaeger_os.agent.dialects import extract_tool_calls
from jaeger_os.agent.schemas.tool_schema import ToolDef
from jaeger_os.core.models.mlx_client import MlxClient

HOME = Path.home()
MODELS = [
    ("E4B-4bit (light)", HOME / ".lmstudio/models/lmstudio-community/gemma-4-E4B-it-MLX-4bit"),
    ("12B-8bit (medium)", HOME / ".lmstudio/models/mlx-community/gemma-4-12B-it-8bit"),
    ("26B-A4B-4bit (heavy)", HOME / ".lmstudio/models/lmstudio-community/gemma-4-26B-A4B-it-MLX-4bit"),
]


# ── A few real tools (the routing the bench measures) ───────────────
class _TimeArgs(BaseModel):
    timezone: str = Field("local", description="IANA tz or 'local'")


class _CalcArgs(BaseModel):
    expression: str = Field(..., description="arithmetic expression")


class _WeatherArgs(BaseModel):
    city: str = Field(..., description="city name")


TOOLS = [
    ToolDef(name="get_time", description="Get the current time in a timezone.",
            args_model=_TimeArgs, fn=lambda **k: "12:00"),
    ToolDef(name="calculator", description="Evaluate an arithmetic expression.",
            args_model=_CalcArgs, fn=lambda **k: "42"),
    ToolDef(name="get_weather", description="Get the weather for a city.",
            args_model=_WeatherArgs, fn=lambda **k: "sunny"),
]

# (prompt, expected tool the model should route to)
CASES = [
    ("What time is it right now?", "get_time"),
    ("What is 21 times 2 plus 5?", "calculator"),
    ("What's the weather in Seattle?", "get_weather"),
    ("What time is it in Shanghai?", "get_time"),
]

SYSTEM = (
    "You are a helpful assistant with access to tools. When the user's "
    "request needs a tool, call it. Do not answer from memory when a tool "
    "applies."
)


def probe(label: str, path: Path) -> dict:
    if not path.is_dir():
        return {"label": label, "error": f"missing dir: {path}"}
    print(f"\n{'='*64}\n{label}\n  {path}\n{'='*64}", flush=True)

    t0 = time.perf_counter()
    try:
        client = MlxClient(str(path), warmup=True)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).splitlines()[0][:120]
        print(f"  LOAD FAILED ({type(exc).__name__}): {msg}", flush=True)
        return {"label": label, "error": f"load: {msg}"}
    load_s = time.perf_counter() - t0

    # Smoking-gun #1: raw generation non-empty (the 0/65 bug = empty here).
    raw = client.chat([{"role": "user", "content": "Say the single word: pong."}],
                      max_tokens=16)
    gen_ok = bool(raw.text.strip())
    print(f"  load {load_s:.1f}s | raw-gen {'OK' if gen_ok else 'EMPTY'!r}: "
          f"{raw.text.strip()[:60]!r}", flush=True)

    # Mirror runtime_bridge.build_adapter exactly.
    adapter = MLXAdapter(
        model=client._mlx_model,
        tokenizer=client._tokenizer,
        model_name=client.model_name,
        defaults={"max_tokens": 512},
        mlx_executor=client._executor,
    )

    ok = 0
    tok_total = 0
    gen_s_total = 0.0
    for prompt, expected in CASES:
        formatted = adapter.format_messages(
            messages=[{"role": "user", "content": prompt}],
            tools=TOOLS, system=SYSTEM,
        )
        ev = threading.Event()
        ts = time.perf_counter()
        out = adapter.call(formatted, ev)
        dt = time.perf_counter() - ts
        text = (out or {}).get("text", "") if isinstance(out, dict) else str(out)
        calls = extract_tool_calls(text)
        got = calls[0]["name"] if calls else "(none)"
        hit = got == expected
        ok += hit
        tok_total += len(text.split())
        gen_s_total += dt
        print(f"    [{'PASS' if hit else 'FAIL'}] {prompt!r:<42} "
              f"→ {got:<12} (want {expected}, {dt:.1f}s)", flush=True)

    tps = (tok_total / gen_s_total) if gen_s_total else 0.0
    return {
        "label": label, "load_s": round(load_s, 1), "gen_ok": gen_ok,
        "route_ok": ok, "route_total": len(CASES),
        "approx_tps": round(tps, 1),
    }


def main() -> None:
    results = [probe(label, path) for label, path in MODELS]
    print(f"\n{'='*64}\nSUMMARY\n{'='*64}", flush=True)
    for r in results:
        if "error" in r:
            print(f"  {r['label']:<22} ERROR: {r['error']}")
            continue
        print(f"  {r['label']:<22} gen={'OK' if r['gen_ok'] else 'EMPTY':<5} "
              f"route={r['route_ok']}/{r['route_total']}  "
              f"load={r['load_s']}s  ~{r['approx_tps']} tok/s")


if __name__ == "__main__":
    main()
