# benchmark/ — JROS benchmark suite

Three complementary surfaces — same engine (`src/jaeger_os/core/bench/`)
underneath, three different operator workflows on top. Both
in-process and subprocess drivers exist; both write to the same
output tree so the history aggregator can pull from either.

| Surface | Driver | When to use |
|---|---|---|
| **Agent tool** | `run_benchmark` (the agent calls it) | "Hey agent, run the benchmark." Quick in-process check against the live model the agent's currently using. |
| **Single-model offline** | `run_flat_bench.py` | Operator wants a fresh cold-load run, full corpus, no agent layer in front. |
| **Multi-model sweep** | `run_model_sweep.py` (via `jaeger bench compare`) | Compare two or more local GGUFs head-to-head. Each model gets a fresh interpreter. |
| **Timing** | `timing/bench.py` | Per-prompt wall-clock, with a historical baseline column. |
| **History** | `jaeger bench history` | Rolling leaderboard across every run on this machine. Reads everything below. |

## Directory layout

```
benchmark/
├── README.md                          ← this file
├── HISTORY.md                         ← (written by ``jaeger bench history --write``)
│
├── run_flat_bench.py                  ← single-model cold-load runner
├── run_model_sweep.py                 ← multi-model sweep driver
│
├── flat/                              ← per-run results, nested by model
│   ├── gemma-4-E4B-it-Q4_K_M/
│   │   ├── 20260527-110000/
│   │   │   ├── rows.jsonl
│   │   │   └── summary.json
│   │   └── 20260527-113000/...
│   ├── gemma-4-26B-A4B-it-Q4_K_M/...
│   └── unknown/                       ← runs before model_name stamping
│
├── sweep/                             ← multi-model sweep artifacts
│   ├── RESULTS_<ts>_level0.md         ← rendered comparison
│   ├── sweep_rows.jsonl               ← raw per-model rows (history aggregator reads this)
│   └── <model>.stdout.log             ← per-model subprocess output
│
├── timing/                            ← per-prompt wall-clock suite
│   ├── BENCHMARK.md                   ← rendered table
│   ├── bench.py                       ← runner
│   └── bench_history.jsonl            ← committed append-only history
│
└── archive/                           ← pre-2026-05-25 frozen artifacts
    └── README.md
```

The layout was restructured 2026-05-27 to nest flat runs under the
model that produced them. **Every new bench run lands at
`<model>/<timestamp>/`** — never at the top of `flat/`. The history
aggregator handles both layouts so older results stay accessible
during the transition.

The suite **code** is committed. The routing suite's **output**
(`flat/<model>/<ts>/rows.jsonl`, `summary.json`) is git-ignored.
The timing suite's `bench_history.jsonl` **is** committed — it is the
append-only historical performance record.

## The flat bench

One canonical corpus of bench cases lives in
[`../src/jaeger_os/core/bench/cases.py`](../src/jaeger_os/core/bench/cases.py).
Each case carries its own scoring rules (expected tools, answer
substrings, hallucination signals, multi-turn session keys), so the
runner is a single uniform pass — no per-level dispatch.

Tags let you run a subset:

- `routing` — single-turn, single expected tool
- `multistep` — single-turn, multiple expected tools (set / ordered)
- `multiturn` — multi-turn scenarios (rows share a session key)
- `recovery` — failure surface + anti-hallucination
- `memory` / `files` / `web` / `code` / `audio` / `schedule` — subsystem

## Running it

### Agent-callable (the live path)

Inside the TUI, just ask:

> "run the system benchmark"

The agent calls the `run_benchmark` tool. Every case fires through
the SAME boot + system prompt + lean surface + dispatch you're
using, which is what makes this the most honest signal. Results land
under `<instance>/logs/bench/<timestamp>/`.

```text
You: run the benchmark with just the routing tag, limit 5
Agent: → run_benchmark(tags="routing", limit=5)
       5/5 cases passed; routing 5/5; answer 5/5; elapsed 18.2s
       full report: <instance>/logs/bench/20260525-141200/
```

### Offline (one boot, the whole corpus)

```bash
python benchmark/run_flat_bench.py              # full corpus
python benchmark/run_flat_bench.py --tags routing
python benchmark/run_flat_bench.py --limit 5    # smoke
```

Writes `benchmark/flat/<model>/<timestamp>/{rows.jsonl,summary.json}`
— nested under the model the run used so a `ls flat/gemma-4-E4B-it-Q4_K_M/`
gives you every run of that model in chronological order.

### Multi-model sweep

For comparing local GGUFs head-to-head — each model gets a fresh
Python interpreter so module-level state doesn't leak. Friendliest
entry point is the picker:

```bash
jaeger bench compare                    # interactive picker
jaeger bench compare --models a,b,c     # scripted
jaeger bench compare --tags routing     # narrow the inner bench
```

The underlying driver is `run_model_sweep.py`; the picker is just
its UX layer. The sweep edits the active instance's `config.yaml`
to point at each model in turn (matches the resolver: `JAEGER_INSTANCE_DIR`
env → `~/.jaeger/instances/<name>/`), restores the original after,
and writes a comparison markdown under `sweep/RESULTS_<ts>.md`.

### Rolling history across every run

```bash
jaeger bench history                    # print the leaderboard
jaeger bench history --write            # also write benchmark/HISTORY.md
jaeger bench history --family gemma     # filter
jaeger bench history --top 5
```

Aggregates `sweep/sweep_rows.jsonl` + every `flat/<model>/<ts>/summary.json`
into a single per-model leaderboard sorted by best routing %.

## The timing suite — `timing/`

A flat per-prompt wall-clock benchmark: a 47-prompt corpus run through
`run_command`, each turn timed. It carries a **`legacy` column** — the
lowest historical total ever recorded per prompt, from
`timing/bench_history.jsonl` (3000+ rows preserved from before the
repo split). That column is the baseline every run is measured against.

```bash
python benchmark/timing/bench.py                # run the 47-prompt corpus
python benchmark/timing/bench.py --render-only   # re-render md from history
```

It writes `timing/BENCHMARK.md` (legacy vs. current) and appends to
`timing/bench_history.jsonl` — the history file **is committed**, so the
performance record grows with the project and never resets.

## Note

Expected-tool names track the live tool surface. After a tool rename,
update the expected values in `src/jaeger_os/core/bench/cases.py` (and
the `UMBRELLA_EQUIVALENTS` map there if it's a consolidation).
