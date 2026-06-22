# Jaeger-OS timing benchmark

Last run: `2026-05-21T02:06:09+00:00` · model: Gemma 4 26B-A4B Q4_K_M · transport: in-process llama-cpp-python.

All numbers are wall-clock seconds for one full prompt turn (decide → tool → optional finalize). The **legacy** column is the lowest historical total ever recorded for `python_jaeger` on that prompt — jaeger_os was forked from python_jaeger, so it IS the historical jaeger performance record. `—` = no historical entry for that prompt.

Regenerate with `python benchmark/timing/bench.py` or `--render-only` to re-render from existing history.

## Per-prompt total seconds

| prompt | expected tool | legacy | jaeger_os |
|---|---|---:|---:|
| what time is it | `get_time` | 0.22 | 1.02 |
| what time is it in shanghai | `get_time` | — | 1.17 |
| calculate 47 times 23 plus 12 | `calculate` | 0.45 | 1.43 |
| calculate the square root of 12345 | `calculate` | 0.44 | 1.44 |
| list the workspace | `list_skill_dir` | — | 0.98 |
| make a file called bench.txt with the message hello from the benchmark | `file_write` | — | 1.49 |
| read bench.txt out loud | `speak_file` | — | 5.60 |
| search the web for recent news about local llms | `web_search` | 5.09 | 6.67 |
| what is the current weather in Seattle | `get_weather` | 1.98 | 1.89 |
| tell me a one sentence story about a robot | _(free-text)_ | 0.49 | 0.65 |
| in three words, what is the capital of France | _(free-text)_ | 0.22 | 0.31 |
| delete bench.txt | `delete_file` | — | 1.00 |
| what is the cpu and disk status of this machine | `system_status` | 0.82 | 3.02 |
| search the web for trending youtube topics about home robots | `web_search` | — | 6.09 |
| write a 4 sentence youtube intro script about a robot named Lilith ... | `file_write` | — | 2.89 |
| append a closing line to youtube_intro.txt asking viewers to subscribe | `append_file` | — | 1.68 |
| narrate youtube_intro.txt out loud as if you are reading it for a y... | `speak_file` | — | 24.19 |
| come up with a catchy youtube title for a video about a robot vacuu... | _(free-text)_ | — | 5.91 |
| delete youtube_intro.txt | `delete_file` | — | 1.15 |
| remember that my preferred youtube video length is 90 seconds | `remember` | — | 1.51 |
| what video length do I prefer? | `recall` | — | 1.13 |
| what do you know about me? | `list_facts` | — | 1.01 |
| forget my video length preference | `forget` | — | 2.10 |
| remember that my favorite color is teal | `remember` | 0.48 | 1.10 |
| what is my favorite color | `recall` | 1.83 | 0.92 |
| search your memory for anything we said about youtube | `search_memory` | — | 1.07 |
| run a python snippet that prints the first 8 fibonacci numbers | `run_python` | — | 4.30 |
| show me what tools you have available | `help_me` | — | 2.02 |
| list any credentials I have stored | `list_credentials` | — | 0.91 |
| reload your skill registry | `reload_skills` | — | 0.86 |
| schedule a prompt with cron expression '0 9 * * *' named bench_test... | `schedule_prompt` | — | 2.61 |
| show me my scheduled prompts | `list_schedules` | — | 1.52 |
| cancel the bench_test schedule | `cancel_schedule` | — | 1.08 |
| **TOTAL** |  | **12.02** | **90.71** |
| **AVG / prompt** |  | **1.20** | **2.75** |

## Headlines

- **jaeger_os** — 33 prompts run; routing OK on **29/33** (88%); total 90.71s, avg 2.75s/prompt.
- **legacy** (python_jaeger) best-of-history — 10/33 prompts covered; total 12.02s, avg 1.20s/prompt.
- **jaeger_os vs legacy:** +129% slower than the historical best.

## How this was generated

- **History file:** `benchmark/timing/bench_history.jsonl` (append-only; this run's rows already landed there).
- **Bench script:** `benchmark/timing/bench.py`.
- **Prompt set:** 33 prompts consolidated from the original 5-way bench + the focused jaeger_os 7-prompt set. See `DEFAULT_PROMPTS` in `bench.py`.
- **Transport:** in-process `llama-cpp-python` for both frameworks. Apples-to-apples on the same model in the same process state.
