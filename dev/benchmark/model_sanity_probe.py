#!/usr/bin/env python3
"""Single-model hardware sanity probe.

Measures whether a model is *healthy on this box* — decoupled from task
performance (which ``run_flat_bench`` covers). Answers what corpus
wall-clock conflates:

  1. **Does it fully fit on the GPU?**  ``offloaded N/M layers to GPU``
     + the Metal-vs-CPU buffer split. A model that spills to CPU
     generates slowly no matter how few MoE experts are active.
  2. **What's the RAW token rate?**  tok/s on a fixed trivial prompt, so
     a 35B-A3B and a 9B are compared on generation speed alone.
  3. **Thinking behaviour — BOTH modes.**  A hybrid thinking model
     (Qwen3.x, etc.) is used two ways: reasoning ON for a deep-think
     agent, OFF for a real-time agent. We measure each separately,
     because "ON" spends hundreds of reasoning tokens (slow wall-clock)
     while "OFF" answers directly (fast). Disable is done by rendering
     the model's own chat template with ``enable_thinking=False`` (the
     llama-cpp chat API won't take it as a kwarg) and running the
     completion path on the rendered prompt.

Run standalone:  ``python model_sanity_probe.py /path/to/model.gguf``
Emits one ``SANITY_JSON:{...}`` line for the sweep driver to collect.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time


# Fixed, trivial prompt so raw tok/s is comparable across models.
_PROMPT = "What time is it in Tokyo?"

# Must match LocalLlamaAdapter._LLAMA_DEFAULTS so the probe measures the
# SAME configuration the agent runs.
_LLAMA_KW = dict(
    n_ctx=8192, n_gpu_layers=-1, n_batch=512, n_ubatch=512, flash_attn=True,
)

_REASON_STARTS = (
    "okay", "here's a thinking", "here is a thinking", "let me think",
    "let me", "first,", "first ", "i need to", "we need to", "alright",
    "the user", "to answer", "<think>",
)


def _load_capturing_stderr(model_path: str):
    """Load while capturing llama.cpp's C-level stderr (fd 2) to parse
    the GPU-offload summary — ``redirect_stderr`` only catches Python."""
    saved_fd = os.dup(2)
    tmp = tempfile.TemporaryFile(mode="w+")
    os.dup2(tmp.fileno(), 2)
    t0 = time.perf_counter()
    try:
        from llama_cpp import Llama
        llm = Llama(model_path=model_path, verbose=True, **_LLAMA_KW)
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)
    load_s = time.perf_counter() - t0
    tmp.seek(0)
    log = tmp.read()
    tmp.close()
    return llm, load_s, log


def _parse_offload(log: str) -> dict:
    info: dict = {"gpu_layers": "?", "full_offload": None,
                  "metal_mb": 0, "cpu_mb": 0}
    m = re.search(r"offloaded (\d+)/(\d+) layers to GPU", log)
    if m:
        on, total = int(m.group(1)), int(m.group(2))
        info["gpu_layers"] = f"{on}/{total}"
        info["full_offload"] = (on == total)
    metal = sum(float(x) for x in re.findall(
        r"(?:MTL\d+|Metal)\w* model buffer size\s*=\s*([\d.]+) MiB", log))
    cpu = sum(float(x) for x in re.findall(
        r"CPU\w* model buffer size\s*=\s*([\d.]+) MiB", log))
    info["metal_mb"] = round(metal)
    info["cpu_mb"] = round(cpu)
    return info


def _thinks(text: str) -> bool:
    low = text.lstrip().lower()
    return ("<think>" in low or "</think>" in low
            or low.startswith(_REASON_STARTS))


def _run_default(llm) -> dict:
    """As-shipped path (create_chat_completion). For a hybrid model this
    is its DEFAULT mode — usually thinking ON."""
    t0 = time.perf_counter()
    r = llm.create_chat_completion(
        messages=[{"role": "user", "content": _PROMPT}],
        max_tokens=512, temperature=0.0,
    )
    dt = time.perf_counter() - t0
    msg = r["choices"][0]["message"].get("content") or ""
    ct = int((r.get("usage") or {}).get("completion_tokens", 0) or 0)
    return _mode_result("default", ct, dt, msg)


def _run_rendered(llm, template_str: str, enable_thinking: bool) -> dict:
    """Render the model's own chat template with ``enable_thinking`` set,
    then run the completion path on the rendered prompt — the only way
    to toggle thinking (the chat API won't take the kwarg)."""
    import jinja2
    env = jinja2.Environment()
    env.globals["raise_exception"] = lambda m: (_ for _ in ()).throw(
        Exception(m))
    tmpl = env.from_string(template_str)
    prompt = tmpl.render(
        messages=[{"role": "user", "content": _PROMPT}],
        add_generation_prompt=True, enable_thinking=enable_thinking,
    )
    t0 = time.perf_counter()
    r = llm.create_completion(prompt=prompt, max_tokens=512, temperature=0.0)
    dt = time.perf_counter() - t0
    txt = r["choices"][0]["text"] or ""
    ct = int((r.get("usage") or {}).get("completion_tokens", 0) or 0)
    return _mode_result("think" if enable_thinking else "direct", ct, dt, txt)


def _mode_result(mode: str, ct: int, dt: float, text: str) -> dict:
    return {
        "mode": mode,
        "tps": round(ct / dt, 1) if dt > 0 else 0.0,
        "gen_tokens": ct,
        "wall_s": round(dt, 1),
        "thinks": _thinks(text),
        "sample": text.replace("\n", " ").strip()[:80],
    }


def probe(model_path: str) -> dict:
    size_gb = round(os.path.getsize(model_path) / 1e9, 1)
    llm, load_s, log = _load_capturing_stderr(model_path)
    off = _parse_offload(log)
    template_str = (llm.metadata or {}).get("tokenizer.chat_template", "") or ""

    # A hybrid thinking model exposes ``enable_thinking`` in its template
    # → measure BOTH modes (deep-think + real-time). Otherwise one run.
    runs: list[dict] = []
    if "enable_thinking" in template_str:
        try:
            runs.append(_run_rendered(llm, template_str, True))
            runs.append(_run_rendered(llm, template_str, False))
        except Exception as exc:  # noqa: BLE001 — template render can fail
            runs = [_run_default(llm)]
            runs[0]["mode"] = f"default (toggle failed: {type(exc).__name__})"
    else:
        runs.append(_run_default(llm))

    return {
        "model": os.path.basename(model_path)[:-5],
        "size_gb": size_gb,
        "load_s": round(load_s, 1),
        "gpu_layers": off["gpu_layers"],
        "full_offload": off["full_offload"],
        "metal_mb": off["metal_mb"],
        "cpu_mb": off["cpu_mb"],
        "hybrid_thinking": "enable_thinking" in template_str,
        "runs": runs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="model-sanity-probe")
    ap.add_argument("model_path")
    args = ap.parse_args()
    try:
        res = probe(args.model_path)
    except Exception as exc:  # noqa: BLE001 — report, never crash the sweep
        res = {
            "model": os.path.basename(args.model_path)[:-5],
            "error": f"{type(exc).__name__}: {exc}",
        }
    print("SANITY_JSON:" + json.dumps(res), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
