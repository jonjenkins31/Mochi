"""Launch an imported mochi-v4 PySide6 window by name.

QUARANTINE: these windows came straight from the v4 archive and still talk the
OLD zmq control plane, so buttons may be inert until rewired to the new bus.
Goal for now is just to SEE + launch them; fine-tune later.

    python -m mochi.interfaces.v4.launch companion   # the 9-page Studio
    python -m mochi.interfaces.v4.launch player       # virtual-display player
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_V4 = Path(__file__).resolve().parent
if str(_V4) not in sys.path:                 # so core.*, transport, siblings resolve by old name
    sys.path.insert(0, str(_V4))

WINDOWS = {
    "companion": "mochi_companion",
    "player": "mochi_vdisplay_player_qt",
}


def launch(name: str) -> int:
    if name not in WINDOWS:
        print(f"unknown window {name!r}; choose: {', '.join(WINDOWS)}")
        return 2
    return importlib.import_module(WINDOWS[name]).main()


if __name__ == "__main__":
    raise SystemExit(launch(sys.argv[1] if len(sys.argv) > 1 else "companion"))
