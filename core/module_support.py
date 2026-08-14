"""Shared helpers for Mochi's imported module integrations.

Provider-named files live under ``modules/``; generic plumbing that is not
itself a module lives here.
"""

from __future__ import annotations

import importlib.util
import threading
from typing import Any, Callable


def installed(package: str) -> bool:
    """Is the module's package importable?

    Module integrations use this to degrade rather than crash. A tab that says
    "no TTS installed" is useful; an ImportError at boot is not, and a
    body must show a face with no voice available.
    """
    try:
        return importlib.util.find_spec(package) is not None
    except (ImportError, ValueError):
        return False


def config_of(app: Any) -> dict:
    """The app's LIVE settings mapping — the one a write must land in.

    `app.config or {}` looks equivalent and is not: an empty dict is
    falsy, so that idiom quietly swapped the real mapping for a
    throwaway and every setdefault wrote into nothing. It only ever
    worked because a manifest usually has tables in it, which is the
    worst kind of bug — correct until the day something starts from
    empty. Identity is what matters here, so the test is `isinstance`.
    """
    config = getattr(app, "config", None)
    return config if isinstance(config, dict) else {}


def settings(app: Any, key: str) -> dict:
    """This module's slice of the app's settings.

    Mirrors the `config_key` in jaeger.toml. A COPY — to change what a
    node will be built with, write into `app.config[key]` itself, which
    is the dict its factory re-reads on every start.
    """
    try:
        return dict(config_of(app).get(key, {}) or {})
    except Exception:  # noqa: BLE001
        return {}


#: The JaegerOS driver that owns the microphone and the speaker. Neither
#: the ears nor the voice open a device; both are silent without it.
AUDIO_NODE = "audio_io"

#: The JaegerOS node that owns the camera. Unlike the audio driver it
#: shares its device with nobody, so switching it needs no reconciling —
#: `set_node()` is the whole story, and there is no `vision_switch.py`.
VISION_NODE = "vision"


def node_state(app: Any, node_id: str) -> str:
    """What the supervisor is doing with one node: "running", "off", or
    "" when this manifest never declared it (sim.toml declares no audio).
    """
    supervisor = getattr(app, "supervisor", None)
    try:
        if supervisor is None or not supervisor.has(node_id):
            return ""
        return "running" if supervisor.is_running(node_id) else "off"
    except Exception:  # noqa: BLE001
        return ""


def set_node(app: Any, node_id: str, on: bool) -> str:
    """Start or stop one supervised node. "" when it happened, else why not.

    BLOCKS for as long as the node's setup takes — opening the mic is
    3.6s on macOS and loading a Whisper model is longer — so call it off
    the GUI thread. A node stopped this way stays stopped: the
    supervisor's watch loop only restarts what it was told to run.
    """
    supervisor = getattr(app, "supervisor", None)
    if supervisor is None or not getattr(supervisor, "has", lambda _: False)(node_id):
        return f"no {node_id!r} node in this manifest"
    try:
        supervisor.start(node_id) if on else supervisor.stop(node_id)
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"
    return ""


def audio_driver(app: Any, *, capture: bool, wanted: bool) -> str:
    """Run the audio driver in the shape its consumers need, or not at all.

    `capture` is read once, when the node is BUILT, so changing it is a
    rebuild — and it is worth the rebuild: a driver that opens the
    microphone so that a reply can be SPOKEN puts a recording indicator
    in the menu bar for the one job that never needed one. That is the
    whole reason the mic and the speakers are two switches.

    "" when it happened, else why not. BLOCKS — opening the device is
    3.6s on macOS.
    """
    if not wanted:
        return set_node(app, AUDIO_NODE, False)
    slice_ = config_of(app).setdefault(AUDIO_NODE, {})
    if (node_state(app, AUDIO_NODE) == "running"
            and bool(slice_.get("capture")) == capture):
        return ""
    slice_["capture"] = capture
    return set_node(app, AUDIO_NODE, False) or set_node(app, AUDIO_NODE, True)


def background(work: Callable[[], str], sink: list) -> None:
    """Run one blocking node switch off the caller's thread.

    Every switch above loads a model or opens a device, and a tab that
    calls one directly freezes the window for as long as that takes. The
    result is appended to `sink` instead of returned, so the tab's
    existing drain timer renders it on the GUI thread — no new timer, no
    signal plumbing, and nothing touching a widget from here.
    """
    threading.Thread(target=lambda: sink.append(work()), daemon=True).start()


__all__ = [
    "installed", "config_of", "settings", "AUDIO_NODE", "VISION_NODE",
    "node_state", "set_node", "audio_driver", "background",
]
