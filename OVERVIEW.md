<h1 align="center">JROS — Jaeger Robot Operating Software</h1>

<p align="center"><em>A Mac-native, Python-first operating framework for embodied AI agents.</em></p>

<p align="center">
  <strong>Local-first.</strong> &nbsp;·&nbsp; <strong>Private by default.</strong> &nbsp;·&nbsp; <strong>One agent, many bodies.</strong>
</p>

> Overview & messaging reference (v0.5.0). Source material for marketing,
> the website, and pitch decks. Everything here ships today.

---

## The one-liner

**JROS is the operating system for AI that lives on your machine and in your robots** — one coherent agent runtime that runs a humanoid's nervous system, a drone's flight deck, or a chat-only desktop companion from the *same* codebase, entirely on-device.

## The pitch

Most "AI agents" are a thin wrapper around someone else's cloud. JROS is the opposite: a **real operating framework** that runs the model *on your hardware*, owns its own tools, memory, and skills, and is built to drive **physical machines**, not just answer chat.

It's the brain **and** the nervous system. The agent loop, memory, and learned skills are the brain; transport, nodes, and topics are the nervous system. The same agent that answers a question in a desktop window can blink an LED face, walk a robot, or fly a drone — because the body is just another surface on the same runtime.

Built from real hardware pain on **Apple Silicon and Jetson Orin** — no Docker, no special OS, no dependency hell. **One curl line installs the whole stack.**

---

## Why JROS is different

| | Most agent tools | **JROS** |
|---|---|---|
| **Where it runs** | Someone's cloud | **On your device** — a local LLM, no account required |
| **Your data** | Leaves your machine | **Stays local** — private by default |
| **What it drives** | A chat box | **Robots + drones + desktops** — one runtime, many bodies |
| **Tools** | Fixed | **~70 built-in + self-authored skills + MCP + plugins** |
| **Extensibility** | Fork it | **Plug in** (MCP, plugins, hooks) *and* **plug JROS into** your editor |
| **Offline** | Breaks | **Works** — the model is on-device |

---

## What it does

### 🧠 A real agent, running locally
- **On-device LLM** — runs entirely on your machine (Apple-Silicon-native MLX or GGUF via llama.cpp). No cloud account, no data leaving the device. Optionally opt into LM Studio, an OpenAI-compatible endpoint, or Anthropic Claude — local stays the default.
- **Swappable inference engines** with host-tier model defaults — JROS picks a model that fits your RAM out of the box, and you can change it in a click.
- **Hermes-class agent loop** — tool dispatch, parallel-safe execution, context compaction, warn-before-halt guardrails, error-classified retry, and graceful interruption.
- **~70 built-in tools across 11 categories** — files (read/write/edit/search), web research, code execution, memory, scheduling, background processes, a Kanban task board, and delegation.
- **89 playbook skills** — curated procedures for non-trivial work (research, productivity integrations, creative, dev workflows), surfaced to the model on demand.
- **Self-authoring skills** — the agent can research, write, smoke-test, benchmark, and version its *own* skills, and a **Deep Think** mode swaps to a heavier coder model during idle time to do it.
- **Computer use** — drives any macOS app through the accessibility tree: see the screen, click, type, work menus.

### 💬 Talk to it however you want
- **Native macOS menu-bar app** (Swift) — avatar, live agent status, a floating ⌥Space quick-input pill, and a settings window.
- **Windowed chat app** (PySide6) — a clean, terminal-styled "rich TUI" window with live tool activity, markdown rendering, slash commands, and multiple conversations.
- **Terminal TUI** — the full Rich/prompt-toolkit experience for the keyboard-first.
- **Avatar renderer** — a native animated face that reacts to what the agent is doing.
- **Voice** — always-on mic with wake-word activation, high-quality Kokoro text-to-speech, and on-device Whisper transcription. Speak to it; it speaks back.
- **Messaging bridges** — reach the agent from Discord, Telegram, or iMessage.

### 🔌 Extensible both ways
- **Use any tool** — JROS is an **MCP client**: connect external MCP servers and the agent gains their tools.
- **Be a tool** — JROS is also an **MCP server** (`jaeger mcp`): drive the agent from Claude Code, Cursor, or Zed as a first-class tool.
- **Plugins & hooks** — third parties add tools, slash commands, and lifecycle hooks via a clean entry-point API — no forking.
- **One client protocol** — every surface (and any you build) speaks the *same* documented wire protocol over a reusable SDK. New front-ends are cheap; the brain never changes.

### 🧩 Built to remember and to ask
- **Durable conversations** — sessions persist to SQLite, so history survives a restart and you can pick a conversation back up.
- **Persistent memory** — facts and episodic memory carry across sessions.
- **Asks before it acts** — when the agent hits something risky, it pauses *mid-task* and asks you to approve, clarify, or supply a secret — then continues.

### 🤖 Embodiment-ready
- **One agent, many bodies** — the same runtime drives a chat window or a robot. A **hardware framework** (nodes, topics, robot packages) and a **capability-gated skill loader** are already in place.
- **6-tier permission ladder** — every tool is gated by risk; high-risk actions are confirmation-prompted and audit-logged. Run it locked-down for a desk companion or trusted-unattended for a robot.

---

## How it's built (for the technically curious)

```
┌──────────────────────────────────────────────────────────┐
│                       SURFACES                            │
│   macOS app · windowed chat · terminal TUI · avatar       │
│   voice · Discord/Telegram/iMessage · MCP · your own      │
└───────────────────────────┬──────────────────────────────┘
                            │  one session-tagged event stream
                            │  (one documented protocol, many transports)
┌───────────────────────────┴──────────────────────────────┐
│                     AGENT (BRAIN)                         │
│   loop · tools · 89 skills · memory · permissions ·       │
│   MCP client · plugins · durable sessions                 │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────┴──────────────────────────────┐
│              NERVOUS SYSTEM (BODY)                        │
│   transport · nodes · topics · hardware packages ·        │
│   animation/avatar · TTS/STT/vision nodes                 │
└──────────────────────────────────────────────────────────┘
```

The agent emits a single **event stream** (replies, live tool activity, state, prompts); every surface just renders it — *"transports, not endpoints."* That's why JROS runs the same brain behind a native app, a terminal, a robot face, or your code editor.

---

## Who it's for

- **Builders of physical AI** — humanoids, drones, LED-faced companions that need a real on-device runtime, not a cloud round-trip.
- **Privacy-first power users** — people who want a capable agent that never sends their files or conversations to someone else's server.
- **Developers** — anyone who wants to plug an extensible, scriptable local agent into their tools (MCP, plugins) — or plug their tools into it.
- **Tinkerers on Apple Silicon / Jetson** — one install, no Docker, runs on the hardware you have.

---

## At a glance

- **Name:** JROS — Jaeger Robot Operating Software
- **Version:** 0.5.0
- **Platforms:** macOS (Apple Silicon) · Linux (Jetson Orin)
- **Runtime:** Python 3.11+, on-device LLM (MLX / GGUF), optional cloud providers
- **License:** Apache-2.0
- **Install:** one `curl` line
- **By:** Jenkins Robotics — [YouTube @Jenkins_Robotics](https://www.youtube.com/@Jenkins_Robotics) · [Discord](https://discord.gg/sAnE5pRVyT) · [GitHub](https://github.com/JenkinsRobotics/JROS)

---

## Taglines to pull from

- *"The operating system for AI that lives on your machine — and in your robots."*
- *"One agent. Many bodies. Zero cloud required."*
- *"Local-first AI that doesn't just chat — it acts, it remembers, and it can drive a robot."*
- *"Your tools plug into it. It plugs into your tools."*
- *"Private by default. Embodied by design."*
