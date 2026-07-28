"""Shared helpers for the module bindings.

Every file in this folder answers one question: *how does Mochi use
that module?* This one holds what they all need, so a binding stays
short enough to read in one sitting.
"""

from __future__ import annotations

import importlib.util
from typing import Any


def installed(package: str) -> bool:
    """Is the module's package importable?

    Bindings use this to degrade rather than crash. A tab that says
    "no TTS installed" is useful; an ImportError at boot is not, and a
    body must show a face with no voice available.
    """
    try:
        return importlib.util.find_spec(package) is not None
    except (ImportError, ValueError):
        return False


def settings(app: Any, key: str) -> dict:
    """This module's slice of the app's settings.

    Mirrors the `config_key` in jaeger.toml, so `[config.animation]`
    reaches `modules/animation.py` and nothing else.
    """
    try:
        return dict((app.config or {}).get(key, {}) or {})
    except Exception:  # noqa: BLE001
        return {}


__all__ = ["installed", "settings"]
