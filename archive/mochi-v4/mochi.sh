#!/bin/bash
# mochi — the operator command (CLI / management side).
#
# Dispatches:
#   ./mochi.sh                   run the ACTIVE agent (CLI; no --instance needed)
#   ./mochi.sh --instance NAME   run a specific agent
#   ./mochi.sh --voice ...       run the agent in voice mode
#   ./mochi.sh instances ...     manage agents: list / create / edit / delete / ...
#   ./mochi.sh skills|personality|status|roadmap|avatar    operator console
#   ./mochi.sh setup [name]      alias of `instances create`
#   ./mochi.sh doctor            environment + readiness check
#
# To launch the windowed app (chat window + menu-bar tray): `python main.py`.
#
# Management subcommands go to the console (mochi.cli); everything else runs
# the agent (mochi.cli.run). Picks the repo's .venv interpreter directly to
# sidestep pyenv shims.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "[mochi] $VENV_PY not found — set up the .venv first" >&2
  exit 1
fi

case "${1:-}" in
  instances|skills|personality|status|roadmap|avatar|prompt|config)
    exec "$VENV_PY" -m mochi.cli "$@" ;;
  setup)
    shift; exec "$VENV_PY" -m mochi.cli instances create "$@" ;;
  bridge)
    # Headless NDJSON stdio bridge — spawned by the native (Swift) app to
    # drive the agent out of process. Not for interactive use.
    shift; exec "$VENV_PY" -m mochi.interfaces.bridge "$@" ;;
  mcp)
    # Expose Mochi as an MCP server (stdio) so Claude Code / Cursor / Zed can
    # drive the agent as a tool. Spawned by the MCP client.
    shift; exec "$VENV_PY" -m mochi.interfaces.mcp_server "$@" ;;
  doctor)
    shift; exec "$VENV_PY" -m mochi.cli.run --doctor "$@" ;;
  help|--help|-h)
    exec "$VENV_PY" -m mochi.cli --help ;;
  *)
    # bare, --instance, --voice, a one-shot prompt, … → run the agent
    exec "$VENV_PY" -m mochi.cli.run "$@" ;;
esac
