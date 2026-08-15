"""Open JaegerAI's avatar surfaces, for looking at.

    python dev/tools/jaeger_ai_windows.py orb
    python dev/tools/jaeger_ai_windows.py player
    python dev/tools/jaeger_ai_windows.py chat

A REVIEW harness, not an integration. JaegerAI is not installed in
Mochi's environment and is not a Mochi module, so this puts its source
on the path and constructs the widget — enough to see the design and
decide whether to keep it, which is the whole ask.

Every one of them takes `ctx=None` and degrades to a placeholder without
a bus, which is what makes this possible at all.

WHAT IS WORTH NOTICING while reviewing. The VoiceOrb reacts to
`/sense/agent_state` and a TTS amplitude — and Mochi already publishes
both, as `/sense/agent_state` and `/act/speech/chunk`. The chunk topic
exists precisely to carry a lip-sync envelope and currently nothing
consumes it. If any of this is kept, the orb is the piece that plugs
straight in.
"""

from __future__ import annotations

import os
import pathlib
import sys

JAEGER_AI = pathlib.Path.home() / "GITHUB" / "JaegerAI"

WINDOWS = {
    "orb": ("VoiceOrb — reactive voice ring",
            "jaeger_ai.interfaces.avatar_player.voice_orb", "VoiceOrb"),
    "player": ("Floating avatar player",
               "jaeger_ai.interfaces.avatar_player.window", "FloatingAvatarPlayer"),
    "avatar": ("Avatar view (the panel alone)",
               "jaeger_ai.interfaces.avatar_player.window", "AvatarView"),
    "chat": ("Avatar + chat — the composed surface",
             "jaeger_ai.interfaces.avatar_chat.window", "AvatarChatWindow"),
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    which = argv[0] if argv else "orb"
    if which not in WINDOWS:
        print(f"unknown window {which!r}; choose: {', '.join(WINDOWS)}")
        return 2
    if not JAEGER_AI.is_dir():
        print(f"JaegerAI not found at {JAEGER_AI}")
        return 2
    sys.path.insert(0, str(JAEGER_AI))
    os.environ.setdefault("JAEGER_AGENT_NO_TOOLS", "1")

    import importlib

    from PySide6 import QtWidgets

    label, module_name, class_name = WINDOWS[which]
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    try:
        widget_class = getattr(importlib.import_module(module_name), class_name)
    except Exception as exc:  # noqa: BLE001 — say WHY, this is a review tool
        print(f"{label}: cannot import — {type(exc).__name__}: {exc}")
        return 1
    try:
        widget = widget_class()
    except TypeError:
        widget = widget_class(None)
    widget.setWindowTitle(f"JaegerAI — {label}")
    widget.resize(max(widget.width(), 420), max(widget.height(), 420))
    widget.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
