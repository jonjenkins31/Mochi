#!/usr/bin/env bash
# Emergency fallback — launch the legacy Tk debug panel.
#
# Background: docs/SUPERSEDE_TK_PLAN.md describes the migration
# from gui/mochi_gui.py (Tk) to gui/mochi_companion.py (PySide6).
# Phase 6 of that plan disabled mochi_gui in config.yaml so
# `python main.py` no longer auto-spawns it.
#
# Use this script ONLY when:
#   - The new companion is broken or missing a feature
#   - You need a known-good control surface to triage
#
# Usage (from project root):
#   ./tools/launch_legacy_tk.sh
#
# Assumes main.py is already running (broker + animation node).

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f gui/mochi_gui.py ]]; then
  echo "[legacy-tk] gui/mochi_gui.py missing — was it deleted?" >&2
  exit 1
fi

# Prefer the venv Python if available; fall back to system.
if [[ -x venv/bin/python ]]; then
  PYTHON="venv/bin/python"
else
  PYTHON="$(command -v python3 || command -v python)"
fi

echo "[legacy-tk] launching gui/mochi_gui.py with $PYTHON"
exec "$PYTHON" gui/mochi_gui.py
