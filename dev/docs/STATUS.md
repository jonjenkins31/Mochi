# Jaeger-OS — Pipeline Runtime-Verification Status

**Date:** 2026-05-31 *(baselined for `0.2.0`)*
**Why this doc:** the two hermes-parity audits
(`hermes_tool_skill_audit.md`, `hermes_internals_audit.md`) compare
*features and architecture* — "does JROS have a 6-tier permission
system?" They do **not** verify *runtime correctness* — whether the
wiring actually works end to end. The permission-prompt bug proved the
gap: every audit said permissions = MATCH, but the confirmation flow was
broken because a code-reading audit cannot see a cross-thread wiring
defect. This doc tracks the **runtime** status of each pipeline — what
has actually been exercised and works.

---

## Pipeline matrix

| Pipeline | Audited vs hermes | Runtime-verified | Status |
|---|---|---|---|
| **Permissions** | ✅ tool/skill #1 | ✅ 2026-05-22 | **Fixed.** Two runtime bugs found + fixed: (1) `install_policy` set a `contextvar` the worker thread never inherited → default `DenyAllProvider`; (2) the TUI confirmation read stdin from the worker thread → answers never captured. Now uses hermes's Event pattern. 11 regression tests. |
| **Tools** | ✅ tool/skill audit | ✅ 2026-05-22 | 62 tools register; read-only tools exercised directly; file / memory / shell paths exercised by the shakedown. |
| **Agentic loop** | ✅ internals A1/#5/#6 | ✅ 2026-05-22 | `_run_via_iter` ran 11 turns through the shakedown — tool calls, skip-final, free-text all worked. Mid-tool interrupt (#6) shipped. The R4–R8 rebuild (A1 + A10 + #5 + #11) is still pending. |
| **Security** | ✅ internals A3/A5/A9, #2/#12 | ✅ 2026-05-22 | Tier gating, the hash-chained audit log, and the credential-read guard all verified live by the shakedown (`file_read_denied` on `credentials/`). Redaction / hardline / file-safety unit-tested. |
| **Skills** | ✅ tool/skill #8/#9, A2 | ✅ 2026-05-22 | `computer_use` registered; `reload_skills` ran; the agent authored `note_v1/SKILL.md`, it was written, audited, and git-committed (`agent: write skills/note_v1/SKILL.md`). |
| **Models** | ✅ this session (llama.cpp + MLX) | ✅ 2026-06-19 | In-process llama-cpp (Gemma-4 26B-A4B) loads in ~2s and runs turns. **Engines are now a swappable layer** (`engine_registry` + `config.runtime`, surfaced via `jaeger runtime` / `/runtime`): `llama-cpp-python` (GGUF), `mlx-lm` (MLX text), `mlx-vlm` (MLX multimodal — 12B-unified validated 2/2 end-to-end). **GGUF is the default, data-backed**: a clean same-machine A/B (26B-A4B, both routing 6/6) measured GGUF 0.53 s/turn vs MLX 2.57 s/turn (~5×; MLX prefill-bound). ⚠️ see finding F1 (exit teardown). |
| **TUI / interfaces / commands** | ✅ prior session (hermes parity) | ◑ partial | Slash commands unit-tested; the permission prompt fixed + tested. The live REPL needs a real terminal — not auto-verifiable; the user runs it. |
| **Plugins** | ✅ internals Part C | ◑ partial | MCP client + messaging bridges have import smoke tests; not deeply runtime-exercised. |

---

## 2026-06-15 — windowed app (Pattern 1) boots through the chassis [core]

JROS's chassis copy (`jaeger_os/app/`) gained the format's Tier-1 **`core`**
role (resynced from `jaeger_app_framework`), and the windowed app now boots
through it instead of a bespoke host:

- **`jaeger_os/app/`** — ported `core.py` (`Core` ABC + `CoreMainThreadError`,
  main-thread-init assertion), `[core]` manifest parsing (`CoreSpec`), the
  `init_core` boot phase (core built on the main thread, after the bus,
  before nodes/surfaces; `core.stop()` before the bus closes), and exports.
  JROS's intentional divergences (no-fcntl lock / `process_slot.py`, simpler
  supervisor, `asyncio`/`tui` event loops) are untouched. **29 conformance
  tests green** (4 new core tests; boot order proven via a bus subscription,
  not a module global — JROS's pytest import layout makes cross-import
  globals two objects).
- **`jaeger_os/agent/loop/agent_core.py`** — `AgentCore(Core)`: folds the old
  `jaeger_os/core/host.py` (deleted) — model boot on the main thread +
  `AgentBridge` + drain-then-cleanup teardown — into the `[core]` role. There
  is now ONE app/host (the chassis); the second `JaegerApp` class is gone.
- **`jaeger.windowed.toml`** — the Pattern-1 manifest (`[core]` + chat window
  + tray, `event_loop = "qt"`, `shell_quits_core = false`). A bare `./launch`
  boots `JaegerApp("jaeger.windowed.toml").run()` via
  `jaeger_os/core/windowed.py`. `./launch --tui` (Pattern 0) is unchanged.
- **chassis fix (upstreamed)** — `JaegerApp.__init__` now honors a manifest
  *file* path (e.g. `jaeger.windowed.toml`), not just a directory's default
  `jaeger.toml`. Fixed in the framework canonical + synced to all copies +
  ported to JROS.

**Runtime status: ◑ partial — headless-verified, GUI walk pending.**
Verified headless (model boot + `run_for_voice` + the Qt loop stubbed):
`JaegerApp("jaeger.windowed.toml").boot()` builds the `AgentCore` on the main
thread, starts the bridge, round-trips `ChatMessage → ChatReply` over the
chassis bus, and drains + cleans up the model on shutdown
(`test_windowed_app.py::test_windowed_manifest_boots_agent_core_over_chassis`).
1559 tests green across app/agent/core/interfaces. **NOT yet runtime-walked**:
a real `./launch` — actual model load, the Qt window + menu-bar tray
appearing, a live chat turn, and tray-persist-on-window-close — needs the
operator's machine (model weights + a display).

## Findings & fixes — 2026-06-12 hardware framework + JP01 sim package (0.5.0)

Implements dev/docs/JROS_HARDWARE_FRAMEWORK_PLAN.md §4.2 steps 1+2.
Everything below is unit-tested (56 new tests, all headless against
MockTransport); **nothing has touched real hardware** — every JP01
controller ships `simulated: true` and the capability tools are
beta-gated (`JAEGER_DEV_MODE=1` to see them) until live-walked.

- **`jaeger_os/hardware/` framework** — `Transport` ABC
  (`SerialTransport` lazy-pyserial, `ZmqReqTransport` with the JP01
  relay target-wrapping + REQ reopen-on-timeout, `MockTransport`);
  `Protocol` ABC (`AsciiBracketProtocol` — the JP01
  `HEADER[payload]\n` dialect with partial-line buffering +
  heartbeat classification; `JsonLineProtocol`); `Link` =
  Transport × Protocol with primary→relay fallback and a
  crash-proof RX reader thread; `load_package` — topology.yaml →
  msgspec-validated `PackageSpec` (unknown fields, dangling
  controller refs, dotless capability names, bad estop scopes, and
  `requires_framework` version mismatches all refuse loudly at load).
- **Capabilities → ordinary tools** — `register_package_capabilities`
  groups `subsystem.action` capabilities into per-subsystem umbrella
  tools (kanban/memory precedent). Dispatch order per call:
  permission tier → e-stop latch (HARDWARE-tier actions fail closed;
  reads and lights keep working; `allow_when_latched` exempts
  `motion.stop`) → link health (offline = typed retryable error +
  `check_fn` hides the tool) → per-action Pydantic validation →
  handler. Nothing raises into the agent loop.
- **Safety** — `/act/estop` latched topic (`EStop` struct) +
  `EStopLatch`: any bus publisher latches; registered node-local L1
  stops run once on engage; release is operator-only (non-operator
  `engaged=False` on the wire is ignored). `/sense/node_health`
  (`NodeHealth`) published at 1 Hz per controller by the package
  runtime. Both structs registered in `TOPIC_TO_CLASS`.
- **Permissions change** — tier 3 (HARDWARE) no longer hard-denies:
  it routes through the confirmation provider like tiers 1/2/4. The
  old unconditional deny was a leftover from the module's
  Lilith-on-a-laptop origin ("reserved for JROS" — this IS JROS).
  Fail-safe unchanged: no provider wired → `DenyAllProvider` refuses.
- **JP01 package** (`hardware/packages/jp01/`) — topology.yaml with
  surveyed truth (ports, bauds, Jetson relay path, no-IMU,
  no-L0-watchdog warning flag); MC01/AVC01/VCC01 adapters that
  implement the generic node Protocols (stock `MotorNode`/`LightNode`
  drive them from `/act/motion`//`/act/light`) plus capability verbs
  and an L1 `estop()`; firmware-shaped `simulator()` responders;
  near-verbatim `devices/` builder ports; `boot.py` resolving the
  topology's `adapter:` refs (declared = wired — no parallel map),
  with atexit teardown that neutralizes motors + blanks LEDs.
- **Agent surface** — `motion` / `lights` / `robot_vision` /
  `telemetry` umbrella tools; `motion.stop` = MM[0,0,0] + L2 latch
  (the agent can always stop, only the operator un-stops).
  `config.yaml: hardware.package: jp01` boots it (warm-job,
  best-effort, degrades per-controller).
- Suite: **2,182 passed** (+57). Pre-existing skips unchanged
  (lilith-face Mochi backdrop, process-slot flake).

---

## Findings & fixes — 2026-06-12 VoiceLLM-updates port (0.5.0)

VoiceLLM (the end-to-end voice testbed) shipped its own review fixes
recently; this pass harvests the ones JROS's voice pipeline needed.
Unit-tested (26 new across voice + MLX tests); **the VAD-behaviour
changes especially need a live mic walk**.

- **MLX stop-marker holdback** — TODAY'S new JROS MLX adapter emitted
  deltas before stop-scanning, so a marker split across two chunks
  ("<|im_" + "end|>") would leak its head into the delta stream — TTS
  reads "<end_of" aloud (VoiceLLM hit exactly this with Kokoro).
  Ported `_scan_stream_text`: text is emitted only once it can no
  longer be a marker prefix; held-back text flushes at stream end.
  Also ported: sampling now builds a proper ``sampler=`` via
  ``make_sampler`` (bare ``temp=`` kwargs silently diverge or
  TypeError on mlx-lm ≥0.21), warning loudly on fallback.
- **Honest voice latency** — JROS had NO speech-end timestamp
  anywhere (the entire listen+STT phase was invisible; flagged in the
  first review). Now: the VAD worker stamps ``speech_end`` the moment
  the silence hangover closes the phrase, ``next_phrase`` stamps
  ``stt_done`` after the accurate pass, both ride the ``Transcript``
  message (new ``speech_end_pc``/``stt_done_pc`` fields, 0.0 =
  unknown), and the voice loop prints + logs
  ``[voice-latency] stt=… agent=… speech-end→speak=…`` right before
  TTS — the number the operator actually FEELS, measured end to end.
- **Short-phrase early commit** — quick utterances ("yes please",
  "good night") commit after 350 ms of silence instead of the full
  700 ms hangover (phrases ≤1.5 s of voiced speech; ``short_phrase_
  max_ms=0`` disables). Direct port of a VoiceLLM operator-feedback
  fix; ~40% snappier on exactly the turns where lag is most felt.
- **Farewell detection** — "good night" exchanges no longer re-open
  the follow-up window to transcribe scissors. BOTH sides must
  mirror (user farewell AND reply acknowledges) before the follow-up
  is suppressed; STT stays on, next real utterance resumes normally.
  New ``core/voice/farewell.py`` (16 patterns).
- **(REMOVED 2026-06-16) Ignored turns no longer re-arm the follow-up
  window** — this and the entire LLM ``<reply>``/``<ignore>`` voice
  gate were removed.  The gate lived in the agent's system prompt, so
  one model did both gatekeeping and tool-calling, and the gate framing
  suppressed tool routing (gemma-4-26B-A4B: 0/3 tool prompts gated on,
  3/3 off).  The agent is now transport-agnostic; ambient filtering is
  VAD + wake word in the voice input layer.  See CHANGELOG `0.5.0`.
- **♪/*-wrapped hallucination ingress filter** — "♪ music ♪" /
  "*coughs*" forms now drop at the non-speech filter (the
  bracket/paren filter didn't cover them).
- **Verified, no port needed:** JROS already pauses the mic
  SYNCHRONOUSLY before TTS (VoiceLLM's bus-round-trip echo race never
  existed here); context-overflow turns already reach TTS as
  speakable text; the ZMQ bus was already real pub/sub.

---

## Findings & fixes — 2026-06-12 MLX-parity pass (0.5.0)

Operator-reported from the first MLX attempt: "didn't call tools
correctly" and "didn't end the loop early when completed, so it lagged
llama.cpp". Both root causes found and fixed; 14 regression tests.
**Needs a live walk with a real MLX model before trusting** (the
streaming loop is exercised against a faked ``mlx_lm`` in tests).

- **Root cause #1 (tools)** — the old ``MLXAdapter`` inherited
  ``HermesXMLAdapter``: EVERY model got hardcoded ChatML markers and
  Hermes-XML tool prose regardless of its training dialect. Rebuilt as
  a sibling of ``LocalLlamaAdapter``: prompt renders through the
  model's OWN chat template (``tokenizer.apply_chat_template``), tools
  present in the model's native dialect (``detect_family`` +
  ``render_tools_for`` + ``textify_tool_history``), with the Hermes
  block as fallback for unknown families (MLX has no structured tools
  channel — the model must ALWAYS see tools somehow). Parse pipeline
  now matches llama.cpp's: think-block strip, drift extraction,
  envelope cleanup, thinking-exhaustion tagging.
- **Root cause #2 (lag)** — ``mlx_lm.generate`` has no ``stop``
  parameter and the old adapter dropped stop sequences, so every call
  ran out the full 4096-token budget after the answer finished.
  Generation now runs ``mlx_lm.stream_generate`` under our own loop:
  stops the moment the family's end-of-turn marker appears
  (``<|im_end|>`` / ``<|eot_id|>`` / ``<end_of_turn>`` / ``</s>``),
  feeds the per-token progress beacon (true no-token-gap stall
  watchdog + real TTFT), emits ``on_delta`` for live consumers, and
  honours interrupts at token boundaries (a pull-based generator
  break is a clean stop — no llama.cpp-style abort flag needed).
- **Bridge wiring** — ``model.backend: mlx_lm`` previously hit the
  bridge's RuntimeError: ``_adapter_for_client`` only knew llama/
  external client shapes, so the MLX backend could not reach the
  agent loop at all post-cutover. It now detects ``MlxClient`` and
  reuses the client's already-loaded model+tokenizer pair (weights
  load once). In-process stall default (120s) applies to MLX like
  llama.cpp.
- **Install + picker integration** — ``mlx-lm`` installed in the venv
  (0.31.3; ``stream_generate`` / ``GenerationResponse`` surfaces
  verified against the adapter) and added to ``requirements.txt``
  behind a Darwin/arm64 platform marker so Linux installs skip it.
  ``/model list`` now shows a **Local MLX models** section (the
  ``discover_local_mlx`` scan existed but was never rendered);
  ``/model use mlx <name>`` switches to the MLX backend (sets
  ``model.backend: mlx_lm`` + the model directory, auto-selects when
  exactly one MLX model is on disk); ``/model use local`` explicitly
  resets ``backend: llama_cpp_python`` (previously switching
  mlx → local would leave the MLX engine pointed at a .gguf); the
  post-switch fallback truth-check treats mlx as a local target so
  it no longer mis-warns. 3 picker tests.

---

## Findings & fixes — 2026-06-12 Hermes-tail pass (0.5.0)

The remaining adoptable Hermes items, operator-approved. Unit-tested
(539 agent+memory+bench tests, 13 new); live walk pending.

- **Cross-restart session continuity** — the clean-slate rule STANDS
  (raw replay bled stale tasks; that fix is preserved). A freshly
  built session agent is instead seeded with one bounded
  `[PREVIOUS SESSION — REFERENCE ONLY]` digest of that session key's
  recent episodic turns (new `mem.recent_qa_pairs` reads the
  human-facing `answer` column) — orientation without task-state
  replay, same anti-stale framing as compaction digests. Kill switch:
  `JAEGER_SESSION_RESUME=0`. Full-fidelity transcript persistence
  (Hermes `hermes_state.py` style) remains future work and would need
  its own design pass.
- **Token deltas to live consumers** — `AgentCallbacks.stream_delta`
  (declared since Phase 5, never wired) now receives text deltas from
  both HTTP adapters as they stream; the loop passes the callback only
  when a listener is installed. The TTS sentence-chunker can now start
  speaking before the answer finishes — CONSUMING the deltas is the
  voice review's work; the agent side is ready. Local in-process llama
  doesn't stream deltas yet (facade is non-streaming; voice review).
- **Partial-stream recovery** — a connection that dies mid-answer
  after text arrived returns the accumulated text
  (`finish_reason="partial_stream"`) instead of burning a retry on
  words the user may have already seen/heard. A half-assembled TOOL
  call always re-raises — truncated arguments never dispatch.
- **File-mutation verifier footer** — failed `write_file` / `patch` /
  `append_file` / `delete_file` calls that were never superseded by a
  later success on the same target append a warning footer to the
  final answer, catching "I've updated the file!" claims over failed
  writes.
- **Thinking-exhaustion detection** — a local reasoning model that
  spends its whole output budget inside `<think>` is now tagged
  (`finish_reason="thinking_exhausted"`) and surfaced plainly in one
  step, instead of entering the continuation-nudge path (which just
  bought more thinking).
- **Reactive compact-on-overflow** — when a SERVER rejects a prompt
  the estimator thought fit (LM Studio/Ollama/llama.cpp 400 wordings),
  the loop tightens the estimator, re-runs the pre-flight trim, and
  retries the SAME adapter once — previously it walked the fallback
  chain with the identical oversized prompt. The calibrator relaxes
  the ratio back from real usage afterwards.

---

## Findings & fixes — 2026-06-12 memory / latency / bench pass (0.5.0)

Unit-tested (526 agent+bench tests, 12 new); live walk pending.

**Memory — from archive to learning (the Hermes-gap fixes):**
- **Known-facts snapshot in the system prompt** — each session agent
  is built with a bounded (≤1.4K chars) block of curated facts,
  user/preference categories first, frozen at construction so the
  prompt stays byte-stable for prefix caching. The agent now KNOWS
  what it remembered instead of only finding what it thinks to
  search for. New facts surface next session.
- **Background memory review** — every 8 operator turns
  (`JAEGER_MEMORY_REVIEW_EVERY`, 0 = off) a daemon thread runs ONE
  bounded model call over the recent transcript and promotes durable
  signals ("call me Jon", "keep answers short") into the facts store
  (≤5 per review, dedup-checked, audit-logged). Polite by
  construction: takes `llm_lock` only if it's free RIGHT NOW — it
  never queues behind (so never delays) a live voice turn; on
  contention it re-arms for after the next turn. Skips deepthink /
  bench sessions.

**Realtime latency:**
- **Real TTFT end-to-end** — `CallProgress` records its first touch;
  all three adapters report `last_ttft_s` (cloud: first stream chunk;
  local: first sampled token ≈ prefill time); the turn carries it
  through `drive_one_turn` into `LatencyReport.decision_ttft`, which
  was a hardcoded 0.0 (data-as-fiction since Phase 6). The "feels
  slower than VoiceLLM" question is now answerable from JROS's own
  numbers.
- **Tool-prose render cache** (LocalLlamaAdapter) — the per-call
  JSON-serialisation of every tool schema into the system prompt is
  now cached keyed by (dialect family, tool names); recomputed only
  when the visible toolset actually changes.
- (Carried from earlier passes, same goal: parallel all-read
  dispatch, prompt-stable facts snapshot, calibrated estimator =
  fewer needless trims, streaming transport = no false stall kills.)

**Benchmark v1.2 — systematic loop-health testing:**
- **Every bench row now carries loop telemetry**: real `ttft_s`,
  `halt_reason`, `iterations`, `skipped_final`. Summary aggregates
  TTFT avg/p50/p95, a halt-reason histogram (a healthy run is ~empty
  — growth is a loop regression even when pass-rate holds), avg
  iterations, and skip-final counts. The bench now measures the
  LOOP, not just the answers.
- **+6 corpus cases**: two 4-tool ordered chains (old ceiling was
  2-3), two parallel all-read batches (tag `parallel` — the latency
  trend shows the concurrent-dispatch win), and a cross-SESSION
  memory pair (fact stored in one session must surface in a FRESH
  session via the facts snapshot or recall — the end-to-end "robot
  actually knows" test). `BENCHMARK_VERSION = "1.2"`.
- Known coverage gaps that need harness mechanics (not just cases),
  deliberately deferred: fault-injection (mock adapters for fallback
  / empty-response paths — covered today by 526 unit tests), mid-turn
  interrupt/steer timing (async harness), context-compaction
  longevity (synthetic 100-turn session builder). Listed in the
  bench-map report; next bench iteration.

---

## Findings & fixes — 2026-06-12 robot-hardening pass (0.5.0)

Operator-directed follow-up to the Hermes-adoption pass. All
unit-tested (488 agent tests, 7 new); live walk pending.

**Parallel tool dispatch (+ its prerequisites):**
- `ToolDef.side_effect` default flipped `"read"` → `""` (unclassified
  = conservative). The old default silently classified EVERY
  unannotated tool as side-effect-free — parallel dispatch would have
  run `speak` concurrently, and the earlier dedup/no-progress gates
  were quietly over-broad. Both registration decorators accept
  `side_effect=`; 21 read-only builtins in `main.py` are annotated
  `side_effect="read"`; `describe_tool` shows "(unclassified)".
- All-read batches (>1 call, every tool explicitly read, none
  interactive) now execute on a thread pool (≤4 workers) — wall-clock
  becomes the slowest call instead of the sum. Prepare/finish stay
  serial and ordered (counters, callbacks, transcript); only the tool
  functions run concurrently. Mixed batches stay fully sequential.
- Locks added around the listen (Whisper) and vision
  (Moondream/SDXL) model-cache singletons — load/swap is atomic
  under multi-instance dispatch. `browser` stays unclassified
  (sequential) by design.

**Mid-turn steer (operator request):**
- `agent.steer(text)` queues guidance into the RUNNING turn; drained
  as a real user message before the next model step. Persists in
  history (it IS user content). `main.steer_active_turn(text)` is the
  process-level hook beside `request_turn_cancel()` — cancel kills,
  steer redirects. Voice/TUI wiring is the voice review's job; the
  mechanism + hook are ready.

**Deep-think LLM compaction digest (operator request):**
- `ContextGuard(summarizer=…)` upgrades stage-2 compaction to an
  LLM-written digest with deterministic fallback on ANY failure.
  Wired ONLY for `deepthink_*` sessions in `main.py` (bounded
  `client.chat`, 400 tokens) — background work where the extra call
  is latency-free. Voice/chat sessions keep the zero-latency
  deterministic digest.

**Memory-system verdict (operator asked to double-check "similar to
Hermes"):** it is NOT similar — JROS is an audit/recall system
(SQLite facts + episodic log + embeddings, retrieval only when the
model explicitly calls `recall`/`search_memory`), Hermes is a
learning system (curated MEMORY.md injected into the system prompt
every session + a background review agent every N turns that promotes
conversational signals into memory). JROS's storage is actually
richer; the gaps are (1) no fact snapshot in the system prompt —
the agent only knows what it thinks to search for, (2) no periodic
background review promoting episodic signals into facts, (3) no
hook from the tool-call audit into fact promotion. Items 1-2 are the
recommended next memory work (not implemented this pass — needs its
own focused treatment).

---

## Findings & fixes — 2026-06-11/12 Hermes-adoption pass (0.5.0)

Side-by-side review of the Hermes agent (the loop's design ancestor,
clean install) against `jaeger_os/agent/` — four deep-dive studies
(loop lifecycle, context compression, tool execution + error taxonomy,
perf + state). Adopted mechanisms below are **unit-tested** (465 agent
tests, 16 new in `test_hermes_adoption.py`); live walk pending.

**Adopted — context (the daily-driver longevity work):**
- **3-stage compaction** replaces drop-only trimming. Stage 1 prunes
  OLD tool-result bodies to one-line stubs (keeping the on-disk
  artifact path, so spilled results stay reachable via `read_file`);
  stage 2 folds dropped turns into one `[EARLIER CONTEXT — REFERENCE
  ONLY]` digest (user asks / tools used / errors hit — deterministic,
  no LLM call, no added voice latency; re-compactions fold the prior
  digest instead of stacking); stage 3 is the typed overflow as
  before. Usually stage 1 alone fits the prompt and ZERO turns are
  lost where all of them used to vanish.
- **Estimator calibration from real usage** — the guard's
  chars-per-token ratio tightens toward the model's actual tokenizer
  each call (EMA, 10% conservative bias, hard clamps), cutting
  needless trims. Calibration data comes from per-call usage, which
  also exposed a real bug: **Anthropic usage was never accumulated**
  (the loop only read dict-shaped `raw`; Anthropic returns a typed
  object) and cache read/write tokens were ignored — both fixed.

**Adopted — loop behaviour (accuracy on weak local models):**
- **Warn-before-halt** — the backstop now injects recovery guidance
  into the tool result one step before halting (incl. "do not abandon
  tools"); halt thresholds unchanged for bench parity.
- **Result-hash no-progress** — identical READ calls only count
  toward the halt when the result is also identical; polling with
  changing results no longer false-halts.
- **Post-tool empty-response nudge** — one synthetic retry when the
  model goes silent right after tool results (classic Qwen/GLM
  stall); the nudge never persists in history.
- **Wind-down grace call** — at max_iterations the agent spends ONE
  toolless call asking the model to summarise progress instead of
  returning `[halted: hit max_iterations]`.
- **Read-batch dedup** — identical read calls inside one assistant
  message dispatch once; every call id still gets a result.

**Adopted — transport + parsing:**
- **Error-classified adapter chain** — exceptions classify via
  `cloud_errors`; rate-limit/transient retry the SAME adapter with
  jittered backoff (interrupt-aware sleeps) before falling back;
  auth/not-found skip straight to fallback. Previously ANY exception
  caused an immediate provider switch. (`retry_utils` was
  exported-but-unused until now.)
- **Surrogate scrub** before every model call — lone UTF-16
  surrogates (clipboard pastes, byte-level reasoning models) crash
  `json.dumps` in provider SDKs on every later call once they enter
  history.
- **Arg-repair upgrades** — bracket-balancing recovers truncated tool
  calls (`{"path": "x", "content": "ab…` cut mid-string); control-char
  escaping handles llama.cpp builds that emit literal tabs/newlines
  alongside other malformations.

**Evaluated, deliberately NOT adopted (with reasons):**
- **Parallel tool dispatch** (Hermes: 8-worker pool + path-overlap
  gating, ~30-50% latency win on multi-tool turns) — BLOCKED on the
  tool-layer singletons (`vision`/`listen`/`browser` module state);
  parallel dispatch would activate those races. Adopt after per-tool
  locks land.
- **LLM-summarised compression** (Hermes stage 2 uses an aux-model
  call, 5-15s) — mid-turn latency spike is wrong for voice; the
  deterministic digest covers the 80% case. Revisit as a between-turns
  background pass if digest quality proves insufficient.
- **Session persistence / parent-session chains** (`hermes_state.py`,
  SQLite + FTS) — real feature gap (restart loses conversation) but
  it's daemon/state architecture, which needs a plan + operator
  approval first.
- **Mid-turn /steer injection** — voice-pipeline review territory.
- Credential pools, provider-specific recoveries (Bedrock/Codex/
  OAuth tiers), image shrinking — not applicable to JROS's provider
  set today.

---

## Findings & fixes — 2026-06-11 agent-loop reliability review (0.5.0)

VoiceLLM-analog hunt over `jaeger_os/agent/` (loop + adapters). All
fixes below are **unit-tested** (445 agent tests passing, 13 new);
**live voice/model walk still pending** — do not call these
operator-verified until a real session exercises them.

**Fixed — silent-permanent-failure class (the operator's #1 bug class):**
- **Poisoned-transcript repair** — `run_turn` now leaves `messages`
  well-formed on EVERY exit path. Previously: an interrupt or backstop
  halt mid-dispatch left assistant `tool_calls` with no tool results,
  and any adapter exception left an orphaned user message — cloud
  providers then 400 on *every* subsequent turn of the session
  (deterministic re-fail until restart). Un-dispatched calls now get
  synthetic "not executed" results; failed turns append a visible
  `[turn failed: …]` note before re-raising.
- **Pre-flight `ContextOverflow` rollback** — the user message is
  popped before the typed error propagates, so an un-trimmable prompt
  isn't sticky. Mid-turn overflow now halts cleanly with a speakable
  explanation instead of raising through the bridge.
- **Empty assistant responses** (no text, no calls) store a
  placeholder instead of an empty message — Anthropic rejects empty
  text blocks on every later call.
- **Pair-aware history clamp** (`main.py`) — the per-session trim now
  drops assistant-tool groups together instead of blind head deletion
  that could orphan tool results (same 400-forever class).

**Fixed — interrupt + watchdog semantics:**
- **Local barge-in works mid-decode** — `LocalLlamaAdapter.call` was
  swapping the real interrupt event for an uncancellable dummy, so a
  voice interrupt did nothing until the generation completed (minutes
  on a reasoning model). The cooperative abort (logits-processor flag
  + join + context reset) now serves interrupts too.
- **Stale detector measures silence, not duration** —
  `interruptible_call` previously timed out on *total elapsed*, so the
  30s HTTP default killed every long answer (and billed it). Adapters
  now report progress: Anthropic + OpenAI-compat stream at the
  transport level (chunks touch a `CallProgress` beacon; the loop
  still gets one whole message), local llama touches it per decoded
  token. Interrupts mid-stream close the HTTP stream — the provider
  actually stops generating.
- **`OpenAIAdapter(streaming=True)` removed** — it sent `stream=True`
  and then parsed the stream object as an empty message (silent total
  failure). Transport streaming replaced it.
- **Per-tool-result cap scales with ctx** — the fixed 24K-char cap
  exceeded the entire prompt budget at ctx=8192; one big `run_shell`
  result could overflow the window mid-turn.
- **Turn-scoped halt text** — an interrupted turn no longer re-speaks
  the *previous* turn's answer; the per-turn message slice survives
  mid-turn history trims (the bridge previously sliced by stale index
  and could lose the whole turn from session history).
- **Mid-session tool registration** — the dispatch map refreshes per
  turn, so a skill activated mid-session becomes dispatchable without
  rebuilding the agent (the comment that claimed this existed pointed
  at a phantom method).

**Added — beta tool gating (operator request, 2026-06-11):**
- ``ToolDef.beta`` + ``JAEGER_DEV_MODE`` env gate (``./launch --dev``
  sets it). Beta tools are
  excluded from the agent's catalogue — invisible to the model AND
  undispatchable — unless dev mode is on, so half-tested tools can't
  break a daily-driver session. Both registration decorators accept
  ``beta=True``; explicit ``tools=[...]`` allowlists bypass the gate;
  the gate re-evaluates per turn (no rebuild needed to flip);
  ``describe_tool`` reports the flag. First users:
  ``set_avatar_state`` + ``play_timeline`` are now actually
  registered as agent tools (commit f768fb7 claimed they were, but
  nothing ever registered them) — marked beta while Mochi is the
  animation testbed; ``package_skill`` + ``benchmark_skill`` marked
  beta while the 0.5.x skill-tree / marketplace work is in flight
  (the proven playbook tools — ``skill``, ``reload_skills``,
  ``list_skill_dir`` — stay un-gated). 4 regression tests.

**Known-not-fixed (flagged, needs operator decision):**
- Voice latency metrics stamp t0 at orchestrator receive
  (`main.py:2298`) — STT + bus-hop time invisible; `LatencyReport`
  TTFT fields hardcoded 0.0. Belongs to the voice-pipeline review.
- Tool-layer singletons (`vision.py`, `listen.py`, `browser.py` model
  caches / session; `skill_registry/toolsets.py` `_active` visibility
  set) are module-global — concurrent multi-instance dispatch races.
- `HermesXMLAdapter` / `MLXAdapter` are exported + tested but never
  constructed in production; HermesXML with an in-process runner would
  reintroduce the zombie-decode-on-stale class (no abort machinery).
- 7 pre-existing `test_lilith_face.py` failures on the branch tip
  (Mochi-style face rewrite changed the backdrop the test asserts) —
  animation scope.

---

## Findings & fixes — 2026-05-22 runtime sweep

**Fixed:**
- **Permission flow** — `core/permissions.py` (process-global policy fallback so worker threads resolve it) + `interfaces/tui/app.py` (`_TuiConfirmationProvider` rewritten to hermes's Event pattern: the worker posts a request and blocks on a `threading.Event`; the REPL routes the user's next typed line back as the answer). This is *the* bug behind every "confirmation refused" the user hit.
- **`_shakedown.py`** — the runtime harness was itself out of date: it installed no permission policy (so `write_file` and every tier-gated path hit `DenyAllProvider`), carried stale tool-name expectations, and aborted at exit. Now installs an allow-all policy, expectations corrected, and `os._exit`s cleanly.

**Noted — not JROS bugs:**
- **F1 — ggml-metal teardown abort.** The in-process llama-cpp model's Metal context aborts (`GGML_ASSERT` in `ggml_metal_device_free`) if torn down by C++ static destructors at interpreter exit — a known upstream llama.cpp issue (PR #17869). The shakedown now `os._exit`s past it; the long-lived TUI frees the client in `JaegerTUI._shutdown` while the interpreter is alive. **If the TUI is ever seen to exit with code 134, apply the same `os._exit(0)`-after-cleanup mitigation in `main.main()`.**
- **F2 — model routing.** The shakedown's local Gemma-4 prefers `execute_code` over the dedicated `get_time` / `calculate` tools and declined `schedule_prompt`. Model behaviour / prompt-tuning, not a broken pipeline — the tools themselves work.

**Cross-thread bug class — contained.** The permission and mid-tool-interrupt bugs were the same class: the concurrent-TUI rebuild moved turns to a worker thread, and state set on the main thread didn't cross. A sweep for `ContextVar` / `threading.local` found **`permissions._current_policy` was the only `ContextVar` in the codebase** — now fixed with a process-global fallback. `_delegate_depth` is intentionally per-thread. No other landmines of this class remain.

---

## Open work (feature-level, tracked in the audits)

- Main-loop R4–R8 rebuild — internals **A1** (context compression) + **A10** (memory pipeline) + tool/skill **#5** (result formatter) + **#11** (result budget).
- tool/skill **#7** (MCP OAuth), **#10** (tool registry).
- **Daemon split — DROPPED 2026-06-14.** JROS converged on fused mode (one process, TUI in foreground). The daemon scaffold (server/client/protocol/lifecycle/attach/event_bus/chat_ops) was removed; its in-process CLI verbs moved to `jaeger_os/cli/verbs/`. Forward direction is the windowed app + tray (see `jaeger.toml`); the `rich_tui` window surface is parked in tree for that rework. Archived brief: `docs/archive/JROS_DAEMON_ARCH_BRIEF.md`.
- **Tool guardrail controller** (review finding #4 — deferred). Loop-backstop still catches the worst case.
- **Parallel tool execution** (review finding #5 — deferred). Read-only / path-disjoint batches.
- **L2 / L3 / L4 bench coverage** with the corrected umbrella-aware scorer. L1 is baselined; deeper levels need a re-run after the scorer's `_UMBRELLA_EQUIVALENTS` map is applied to L2/L3/L4 modules.

---

## 0.1.0 ship-state — what landed this cycle

**Tests:** 997 passing. (Was ~533 at the prior STATUS snapshot.)

**Major adds:**
- **Daemon scaffold + macOS tray** (`jaeger_os/daemon/`, `jaeger_os/interfaces/tray/`). Lifecycle CLI: `jaeger start | stop | status | restart`. Phase 1.6 tray icon talks to the daemon via the same socket. **Agent still lives in the TUI process.** — **Removed 2026-06-14:** the daemon arch was dropped; `jaeger_os/daemon/` is gone, its in-process verbs moved to `jaeger_os/cli/verbs/`, and the tray is parked for the windowed-app rework.
- **Pre-flight context guardrail** (`src/jaeger_os/agent/util/context_guard.py`). Prevents the "Requested tokens exceed context window" hard fail by trimming history before the call; raises typed `ContextOverflow` when even max trim won't fit. Per-tool-result truncator caps oversized payloads. Group-aware trim preserves tool-call/result pairs.
- **Lean tool surface** (`describe_tool`, catalog injection in system prompt) — **opt-in via `JAEGER_TOOLSET_SCOPING=1`**, default OFF per the 0.1.0 bench data. Infrastructure ready, default revert documented in `docs/lean_surface.md`.
- **Kanban grid view** for `/board` — Rich `Columns` + `Panel`, 5-column layout. Replaces the prior vertical list.
- **`remote_terminal` SSH tool** — Tier-4 wrapper around `ssh user@host -- <cmd>` with `BatchMode=yes` + `ConnectTimeout=10` pinned. Inbound covered by plain sshd + tmux (see `docs/remote_access.md`).

**Bug fixes from the 2026-05-24 code review** (see `docs/code_review_2026_05_24.md`):
- `reset_read_tracker()` called at the top of every `run_turn` (was leaking across turns).
- `AgentInterrupted` now sets `last_halt_reason="interrupted"` at both interrupt sites (was empty assistant message with no halt_reason).
- Tool-name normalization runs at the loop boundary against the registered set (was raw drift names landing in dispatch).
- Skip-final short-circuit suppressed when the user prompt has multi-step intent (was prematurely ending chained tasks).
- Permission / safety errors now tag `error_type` + `retryable` + (optional) `required_tier` (was generic stringified exception).
- Three Laws block wraps every system prompt via `with_three_laws()`.
- Tool-time and loop-time captured in `LatencyReport` (was both 0.0).

**TUI status-bar fixes:**
- Loaded ctx (from `client.loaded_ctx`) shown instead of just config ctx.
- `/runtime` surfaces "model trained for up to N tokens — bump config.model.ctx" when loaded < native.
- 0%-gauge bug fixed: estimator now walks both the Phase-9 dict message shape AND the legacy pydantic-ai `msg.parts[].content`.

**Drift parser:**
- Loose `<function=…>` form (Qwen3-Coder emits this without the `<tool_call>` wrapper) is now salvaged. Was leaking tool-call XML into chat text.

**Bench infrastructure:**
- `benchmark/run_model_sweep.py` drives multi-model comparisons; YAML-aware config-swap; multi-level row parser.
- Scorer in `level1_routing.py` accepts umbrella forms (`memory` for the five fine-grained memory verbs, `execute_code` for `run_python`).
- L1 baseline in `benchmark/levels/history/BENCHMARK_v0.1.0_baseline.md`.

**Model recommendation (from `BENCHMARK_v0.1.0_baseline.md`):**

| Use case | Model |
|---|---|
| **Default / voice-interactive** | gemma-4-E4B-it-Q4_K_M (97.1% routing, 1.6s p50, 5.3 GB) |
| Conservative default | gemma-4-26B-A4B-it-Q4_K_M (97.1%, 3.0s p50, 15.7 GB) — current JROS default |
| Deep Think coder | Qwen3-Coder-30B-A3B (94.1%, 3.2s p50, 18.6 GB) — already the configured coder |
| Smallest viable | gemma-4-E2B-it-Q4_K_M (94.1%, 1.2s p50, 3.4 GB) |
