#!/usr/bin/env bash
# Mochi 3.0 (frozen copy of main @ 09f13c7). Reuses the v4 venv at ../../venv.
cd "$(dirname "$0")" && exec ../../venv/bin/python main.py "$@"
