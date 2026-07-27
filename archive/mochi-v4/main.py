#!/usr/bin/env python3
"""Mochi — run the app.

    python main.py        # launch Mochi (chat window + menu-bar tray)

One root entry, mochi-v4 style: hand off to the chassis. ``JaegerApp`` boots
the agent core (the model, on the main thread) plus the PySide6 surfaces
declared in ``mochi.windowed.toml``, and owns the Qt loop until quit.

The active instance is resolved from ``.mochi/active_instance`` (set by
``./mochi.sh setup``) — no ``--instance`` plumbing here. For the CLI /
management side (doctor, setup, instances, voice), use ``./mochi.sh``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _ensure_venv() -> None:
    """Re-exec under the repo's ``.venv`` (3.11) when launched by any other
    interpreter — system python, a pyenv shim, or the stale 3.13 ``venv/``.
    So ``python main.py`` Just Works regardless of what's on PATH or active.
    """
    venv = PROJECT_ROOT / ".venv"
    venv_py = venv / "bin" / "python"
    if venv_py.exists() and os.path.realpath(sys.prefix) != os.path.realpath(venv):
        os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


def main() -> int:
    _ensure_venv()
    from mochi.core.windowed import main as boot_app
    return boot_app()


if __name__ == "__main__":
    raise SystemExit(main())
