# JROS architecture — system, runtime, user

This is the canonical reference for the three-layer model JROS follows.
Every persistent file in a JROS deployment belongs to exactly one of
these layers, and **the boundaries are the contract** — the upgrade
guarantee, the multi-instance guarantee, and the "where do I put my
stuff" answer all derive from them.

If you're trying to figure out where something should live, read this
doc first.

---

## TL;DR

| Layer | Where it lives | Who owns it | Touched by upgrades? |
|---|---|---|---|
| **System** | `site-packages/jaeger_os/` (or your `git clone` for dev) | JROS the project | Yes — that's the upgrade |
| **Runtime** | `~/.jaeger/instances/<name>/` | JROS at runtime | Schema migrated; content preserved |
| **User** | `~/jaeger/agents/<name>/` (default; configurable) | The end user | **Never** |

If the boundaries blur in your head, default to: *can the upgrade safely
delete this?* If yes → System or Runtime. If no → User.

---

## The OS analogy

JROS borrows the multi-user OS pattern — same one Windows, macOS, and
Linux use — translated to agent personalities instead of human users.

| Concern | macOS | Windows | Linux | **JROS** |
|---|---|---|---|---|
| System | `/System/`, `/Library/` | `C:\Windows\` | `/usr/`, `/etc/` | JROS package (pip / clone) |
| Per-user data | `~/Library/Application Support/<App>/` | `%LOCALAPPDATA%\<App>\` | `~/.config/<app>/` | `~/.jaeger/instances/<name>/` |
| User home | `/Users/<name>/` | `C:\Users\<name>\` | `/home/<name>/` | `~/jaeger/agents/<name>/` |
| What survives upgrades | Everything in `/Users/` | Everything in `C:\Users\` | Everything in `/home/` | Everything in `~/jaeger/` |

A macOS upgrade rewrites `/System/`, may migrate `~/Library/Application
Support/`, and leaves `/Users/<name>/` alone. Same shape applies to
JROS upgrades.

---

## Layer 1 — System

**What it is:** the JROS library — code, built-in skills, built-in
prompts, the model registry, the catalog of tools, the bench
infrastructure, the agent loop, the daemon, the persona schema, the
config schema, all the defaults.

**Where it lives:**
- After `pip install jaeger-os`: `site-packages/jaeger_os/`
- Editable / dev clone: `<repo>/src/jaeger_os/`

**Who owns it:** the JROS project. Every upgrade replaces it.

**What's NOT in System:**
- The user's persona JSON. Those go in User.
- The user's custom skills. Those go in User.
- Memory, logs. Those go in Runtime.
- Model weights downloaded for actual use. The *registry* of models
  is in System; the *weights* live in `~/.jaeger/models/` (Runtime).

**Sub-structure (inside the package):**
```
src/jaeger_os/
├── agent/             agent loop, tool dispatch, parser dialects
├── core/              instance schemas, persona/skill loaders, prompts
├── daemon/            jaeger-daemon process + the bench history verb
├── interfaces/        TUI, tray, rich_tui
├── skills/            built-in skills shipped with JROS
├── models/            model registry + bundled default seeds
├── plugins/           pluggable transports / TTS / STT
└── prompts/           system-level prompt templates
```

---

## Layer 2 — Runtime

**What it is:** per-instance state JROS creates and manages while an
agent is running. Memory, logs, config, the SQLite DB, the cron
schedule, the kanban board, the agent's session history.

**Where it lives:** `~/.jaeger/instances/<instance_name>/`

Hidden by design — it's not meant for direct human editing. JROS
writes here, migrates schemas here, garbage-collects here.

**Sub-structure (per instance):**
```
~/.jaeger/instances/<name>/
├── config.yaml           machine-edited; reflects the user's wizard answers
├── identity.yaml         persona-bound info (mode, voice, agent name)
├── memory/
│   └── state.db          SQLite — facts, episodic, schedules, sessions, tool calls
├── logs/
│   ├── audit.log         JSONL — every tool call + permission decision
│   └── runtime/          rotating agent logs
├── profiles/             ← USUALLY pulled from User layer
├── skills/               ← USUALLY pulled from User layer
├── prompts/              ← USUALLY pulled from User layer
└── workspace/            ← USUALLY pulled from User layer
```

The last four are JROS-standard paths. Their *contents* come from the
User layer (see Layer 3). They're not symlinked at the OS level by
default — JROS reads from the configured `user_dir` (introduced in
0.2.1) and presents the contents under these paths to the rest of the
runtime.

**Multi-instance:**
- `~/.jaeger/instances/lilith/` and `~/.jaeger/instances/eren/`
  coexist with completely separate Runtime state.
- They share the **System** layer (one JROS install).
- They each point at their own **User** dir (`~/jaeger/agents/lilith/`
  and `~/jaeger/agents/eren/`).

**Update contract:**
- JROS may **rename / add / restructure** any directory or file here
  between minor releases (0.2 → 0.3).
- A migration script will preserve user content (memory, etc.) — but
  the *layout* is JROS's to change.
- Operator should not hand-edit files here unless documented as
  user-editable (e.g. `config.yaml`).

---

## Layer 3 — User

**What it is:** what the user actually authors and owns. The persona
that defines this agent's personality, the custom skills the user
wrote, prompt overlays they tuned, the collaboration workspace where
the agent and the user exchange files.

**Where it lives:** `~/jaeger/agents/<agent_name>/` by default. Each
agent is fully isolated from every other agent.

The default location is *visible* (under `~/jaeger/`, not `~/.jaeger/`)
because users need to interact with it directly. The location is
**configurable per instance** — point it at a git repo, a Dropbox
folder, a shared NFS mount, wherever.

**Sub-structure (per agent):**
```
~/jaeger/agents/<name>/
├── persona.json          this agent's persona definition
├── skills/               agent-specific custom skills
│   └── <skill_name>/
├── prompts/              persona prompt overlays
│   └── *.md
└── files/                agent ↔ user collab area (drafts, outputs, scratch)
```

**Why per-agent isolation, not shared:**

Each agent is a separate *personality* — Lilith and Eren aren't two
copies of the same persona, they're different characters. Their
skills are shaped by who they are; mixing them is like installing
Alice's screensaver on Bob's account. Same for prompts. Same for
collab files.

If a skill is truly generic (web_search, calculate, file_io), it
belongs in the System layer — JROS ships it, every agent gets it for
free. The User layer is for agent-specific content.

**Portability:**

Each agent folder is self-contained — zip `~/jaeger/agents/lilith/`,
hand it to someone, they unzip it into their `~/jaeger/agents/`, and
they have your Lilith. No additional state to track.

**Update contract:**

JROS **never modifies** the User layer. Period.

If a 0.X.Y release needs to migrate something here (e.g. a persona
schema change), it does so **only** via an explicit, opt-in command
the user runs (`jaeger user migrate`). Automatic, silent rewrites of
files under the user's purview are forbidden.

---

## Resolution — how JROS finds your stuff

When the agent loop needs to load a persona, a skill, or a prompt
overlay, it follows this resolution chain (introduced in 0.2.1):

```
1. The instance's config.yaml:        user_dir: <path>
2. Default:                            ~/jaeger/agents/<instance_name>/
```

A new helper, `resolve_user_dir(instance_name)`, returns the
effective path. Loaders read from there. The runtime instance dir
(`~/.jaeger/instances/<name>/`) only contains *runtime state* —
nothing the user authored.

**For Lilith-AI as the reference implementation:**

The Lilith-AI repo's root *is* the user dir. `config.yaml` in
`~/.jaeger/instances/lilith/` sets:

```yaml
user_dir: ~/GITHUB/Lilith-AI
```

…and JROS reads `persona.json`, `skills/`, `prompts/`, `files/`
directly from the repo. Users can git-commit their persona changes,
share the repo, etc. Updates to JROS itself never touch the repo.

---

## What about model weights?

Model weights are heavy (1-30 GB each) and shouldn't be in any of the
three layers as designed:

- **Not System** — would bloat the pip wheel by orders of magnitude.
- **Not Runtime** (per-instance) — duplicated across every instance.
- **Not User** — they're not user-authored; they're catalog data.

JROS uses a fourth de-facto layer:

```
~/.jaeger/models/                ← shared model store
  └── <model_key>/<file>.gguf
```

This is system-shared cache state. It survives instance deletions and
is referenced by the model registry in System. The registry knows
which keys map to which downloadable URLs; runtime fetch logic
populates the store on demand.

Existing operator caches (`~/.lmstudio/models/`) are also scanned via
the `extra_gguf_dirs` config option so users don't redundantly
download what they already have.

---

## Examples — putting it all together

### Solo developer, single agent (the common case)

```
SYSTEM:    pip install jaeger-os → site-packages/jaeger_os/
RUNTIME:   ~/.jaeger/instances/lilith/   (created by wizard)
USER:      ~/jaeger/agents/lilith/        (created by wizard or you)
```

After upgrade to JROS 0.3.0:
- `site-packages/jaeger_os/` ← replaced
- `~/.jaeger/instances/lilith/` ← schema migrated, content preserved
- `~/jaeger/agents/lilith/` ← **untouched**

### Multi-agent on one machine

```
~/.jaeger/instances/
  ├── lilith/                   ← her runtime state
  └── eren/                     ← his runtime state

~/jaeger/agents/
  ├── lilith/                   ← her persona + skills + files
  └── eren/                     ← his persona + skills + files
                                  (totally separate from Lilith's)
```

Both share the same System (one JROS install). Both have isolated
Runtime + User layers.

### Project-repo pattern (Lilith-AI)

```
~/GITHUB/Lilith-AI/             ← git repo IS the User layer
  ├── persona.json
  ├── skills/
  ├── prompts/
  └── files/

~/.jaeger/instances/lilith/
  └── config.yaml has: user_dir: ~/GITHUB/Lilith-AI
```

Same separation, just the User layer lives in a versioned project
directory. Pushing the repo lets someone else pull and run your
Lilith with two commands.

---

## What this means for upstream development

When writing a new feature, ask which layer it belongs to **before**
deciding the file path:

- Does the feature change for every agent? → System (in the package).
- Does the feature track per-agent runtime state? → Runtime
  (`<instance_dir>/...`).
- Does the user need to author or share it? → User (`<user_dir>/...`).

If the feature spans layers (e.g. a new skill the user customises),
ship a **default in System** and let the user **override in their User
dir**. The loader's resolution chain handles the fall-through.

---

*Last updated: 2026-05-31 (JROS 0.2.1 introduced the `user_dir`
config option and `resolve_user_dir()`. Prior to 0.2.1, persona /
skills / prompts were read directly from the runtime instance dir;
JROS will migrate existing instances to the new layout on first
0.2.1 launch.)*
