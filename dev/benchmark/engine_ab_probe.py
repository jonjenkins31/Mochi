#!/usr/bin/env python3
"""Clean engine A/B — same 26B-A4B weights, both in-process, through the
REAL make_client → engine_registry → adapter pipeline. GGUF (llama.cpp,
the legacy engine) vs MLX (Apple-native, the new one).

Sidesteps the flaky full-bench harness; loads each engine sequentially
(freeing the first before the second so two 16 GB models never co-resident)
and routes the same cases through each engine's adapter.

  python dev/benchmark/engine_ab_probe.py
"""

from __future__ import annotations

import gc
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field

from jaeger_os.agent.loop.runtime_bridge import _adapter_for_client
from jaeger_os.agent.schemas.tool_schema import ToolDef
from jaeger_os.core.instance.schemas import Config
from jaeger_os.main import make_client

HOME = Path.home()
GGUF = HOME / ".lmstudio/models/lmstudio-community/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-Q4_K_M.gguf"
MLX = HOME / ".lmstudio/models/lmstudio-community/gemma-4-26B-A4B-it-MLX-4bit"


class _T(BaseModel):
    timezone: str = Field("local")


class _C(BaseModel):
    expression: str = Field(...)


class _W(BaseModel):
    city: str = Field(...)


TOOLS = [
    ToolDef(name="get_time", description="Get the current time.", args_model=_T, fn=lambda **k: "12:00"),
    ToolDef(name="calculator", description="Evaluate arithmetic.", args_model=_C, fn=lambda **k: "42"),
    ToolDef(name="get_weather", description="Get weather for a city.", args_model=_W, fn=lambda **k: "sunny"),
]
CASES = [
    ("What time is it right now?", "get_time"),
    ("What is 21 times 2 plus 5?", "calculator"),
    ("What's the weather in Seattle?", "get_weather"),
    ("What time is it in Shanghai?", "get_time"),
    ("Compute the square root of 144.", "calculator"),
    ("Is it raining in London?", "get_weather"),
]
SYSTEM = ("You are a helpful assistant with tools. When a request needs a "
          "tool, call it. Do not answer from memory when a tool applies.")


def _config(model_path: str, mlx_engine: str = "auto") -> Config:
    return Config.model_validate({
        "instance_name": "abprobe",
        "model": {"model_path": model_path},
        "runtime": {"mlx_engine": mlx_engine},
    })


def run_engine(label: str, model_path: str) -> dict:
    if not Path(model_path).exists():
        return {"label": label, "error": f"missing: {model_path}"}
    print(f"\n{'='*60}\n{label}\n{'='*60}", flush=True)
    t0 = time.perf_counter()
    client = make_client(_config(model_path), warmup=True)
    load_s = time.perf_counter() - t0
    adapter = _adapter_for_client(client, system_prompt=SYSTEM)

    ok = 0
    gen_s = 0.0
    toks = 0
    for prompt, expected in CASES:
        fm = adapter.format_messages(
            messages=[{"role": "user", "content": prompt}],
            tools=TOOLS, system=SYSTEM,
        )
        ts = time.perf_counter()
        out = adapter.call(fm, threading.Event())
        dt = time.perf_counter() - ts
        # parse_response handles BOTH tool dialects: GGUF/llama.cpp returns
        # structured tool_calls; MLX returns in-text <tool_call> blocks.
        msg = adapter.parse_response(out)
        calls = msg.get("tool_calls") if isinstance(msg, dict) else None
        got = calls[0]["name"] if calls else "(none)"
        hit = got == expected
        ok += hit
        gen_s += dt
        usage = getattr(adapter, "last_usage", None) or {}
        comp = usage.get("completion_tokens")
        if comp:
            toks += int(comp)
        print(f"  [{'PASS' if hit else 'FAIL'}] {prompt!r:<38} → {got:<12} {dt:.2f}s", flush=True)

    tps = toks / gen_s if gen_s else 0.0
    p_avg = gen_s / len(CASES)
    # Free before the next 16 GB model loads.
    try:
        ex = getattr(client, "_executor", None)
        if ex is not None:
            ex.shutdown(wait=True)
    except Exception:  # noqa: BLE001
        pass
    del adapter, client
    gc.collect()
    return {"label": label, "load_s": round(load_s, 1), "route_ok": ok,
            "route_total": len(CASES), "avg_s": round(p_avg, 2),
            "approx_tps": round(tps, 1)}


def main() -> None:
    results = [
        run_engine("GGUF · llama.cpp (legacy)", str(GGUF)),
        run_engine("MLX · mlx-lm (new, Apple-native)", str(MLX)),
    ]
    print(f"\n{'='*60}\nENGINE A/B — gemma-4-26B-A4B, same weights\n{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  {r['label']:<34} ERROR {r['error']}")
            continue
        print(f"  {r['label']:<34} route {r['route_ok']}/{r['route_total']}  "
              f"avg {r['avg_s']}s  ~{r['approx_tps']} tok/s  load {r['load_s']}s")


if __name__ == "__main__":
    main()
