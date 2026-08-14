"""The ears — how Mochi uses the STT module.

    slot: stt                jaeger-whisper-stt fills it today
    consumes  /sense/mic/pcm
    produces  /sense/stt/transcript, /sense/stt/speech_start

OPTIONAL, like the voice.

WHY THE MIC TOPIC IS LISTED HERE and not only under the audio driver:
"the agent cannot hear me" has three different causes — no audio
driver, a muted device, or an STT that is not running — and they are
indistinguishable from a log of transcripts. A surface that watches
BOTH the raw mic and the transcripts can tell them apart, so this
imported-module integration exposes both.
"""

from __future__ import annotations

import math
import struct
from typing import Any

from jaeger_os import topics

from core.module_support import (
    config_of, installed, node_state, set_node, settings)

SLOT = "stt"
PACKAGE = "jaeger_whisper_stt"

#: The node id jaeger.toml gives this slot — what the supervisor answers to.
NODE = "stt"

#: What a surface watches. The mic frame is in here on purpose — see
#: the module docstring.
WATCH = (
    topics.SENSE_MIC_PCM,            # is the microphone alive at all?
    topics.SENSE_STT_SPEECH_START,   # the VAD says you started talking
    topics.SENSE_STT_TRANSCRIPT,     # what it thinks you said
)

#: Named on its own because a surface that ROUTES heard speech somewhere
#: — the Chat tab handing a turn to the mind — wants this one topic and
#: not the meter's mic frames.
TRANSCRIPT = topics.SENSE_STT_TRANSCRIPT


def available() -> bool:
    return installed(PACKAGE)


# ── which pipeline ───────────────────────────────────────────────
#
# Whisper is not one algorithm here: the module ships several
# segmentation strategies (VAD-closed phrases, a fast/accurate two-pass,
# rolling re-transcription, word-cursor streaming) and they trade
# latency against accuracy differently enough that the right one is a
# question about the room, not a default. So it is a picker, not a
# setting buried in the manifest.

def modes() -> tuple[tuple[str, str], ...]:
    """(name, what it does) for every pipeline the installed STT offers.

    Read from the module's own registry rather than listed here, so a
    method it gains or drops shows up in Mochi without an edit.
    """
    if not available():
        return ()
    try:
        from jaeger_whisper_stt.engine.registry import METHODS
    except Exception:  # noqa: BLE001 — a broken engine must not kill a tab
        return ()
    return tuple((m.name, m.desc) for m in METHODS.values())


def mode(app: Any) -> str:
    """Which pipeline the ears would be built with right now."""
    return str(settings(app, NODE).get("stt_mode", "")) or "two_pass"


def set_mode(app: Any, name: str) -> str:
    """Swap the pipeline. "" when it happened, else why not. BLOCKS.

    The mode is read once, when the node is BUILT, so a live swap is a
    restart. There is no reconfigure topic and inventing one would move
    engine state into the app — the supervisor already knows how to
    rebuild a node from its config, which is the whole trick.
    """
    # The live slice, not `settings()`'s copy: this dict is the one the
    # node's factory re-reads on every start.
    config_of(app).setdefault(NODE, {})["stt_mode"] = name
    if not listening(app):
        return ""            # takes effect the next time the ears start
    return set_node(app, NODE, False) or set_node(app, NODE, True)


# ── not hearing ourselves ────────────────────────────────────────
#
# The single hardest bug in a voice loop: the character speaks, the
# microphone hears it, the STT transcribes it, the mind answers it, and
# it never stops. The engine ships both defences and NOTHING was calling
# them, which is why it looped.
#
# These reach into the live node object rather than going over a topic,
# because there is no topic for either one. That is allowed HERE and
# nowhere else — this file exists to be the single named place Mochi
# touches this provider, the same licence `modules/jaeger_agent.py` uses
# to import `jaeger_agent.messages`. A tab must never do this.

def _session(app: Any) -> Any:
    """The live AudioSession inside the running stt node, or None.

    Defensive to the point of paranoia on purpose. This is called from
    the reply path, and an AttributeError here does not fail a gate — it
    propagates out of a bus subscriber and the reply is never spoken at
    all. `None` means "no ears to pause", which is the normal state
    every time the microphone is off.
    """
    supervisor = getattr(app, "supervisor", None)
    getter = getattr(supervisor, "node", None)
    if getter is None:
        return None
    try:
        return getattr(getter(NODE), "session", None)
    except Exception:  # noqa: BLE001
        return None


def pause(app: Any, paused: bool) -> bool:
    """Stop feeding the VAD while the character is talking. True if taken.

    A real pause, not a filter on the far end: the engine drains its
    buffer on the boundary, so the reply's tail cannot be spliced onto
    the front of whatever you say next — and Whisper is not asked to
    decode our own voice at all.
    """
    session = _session(app)
    if session is None:
        return False
    try:
        session.set_paused(bool(paused))
    except Exception:  # noqa: BLE001 — never let a gate kill the loop
        return False
    return True


def open_followup(app: Any) -> bool:
    """Let the next thing you say skip the wake phrase. True if taken.

    voice_assistant.py's follow-up window: after a reply the assistant
    stays open for `followup_window_s` so a conversation does not need
    "hey mochi" in front of every sentence. The engine implements it and
    exposes the trigger; calling it is the app's job, because only the
    app knows when the reply is over. A no-op when the mode does not
    gate on a wake phrase, which is what makes it safe to call blindly.
    """
    session = _session(app)
    adapter = getattr(session, "adapter", None)
    opener = getattr(adapter, "open_followup", None)
    if opener is None:
        return False
    try:
        opener()
    except Exception:  # noqa: BLE001
        return False
    return True


def remember_reply(app: Any, text: str) -> bool:
    """Tell the engine what we just said. True if taken.

    Its self-speech filter compares each phrase against this and drops
    close matches. It defaults ON and was inert because the field was
    never set — the backstop for whatever leaks past the pause, which on
    a speaker loud enough to reach the mic during the unpause window is
    not hypothetical.
    """
    session = _session(app)
    if session is None:
        return False
    try:
        session.remember_reply(text or "")
    except Exception:  # noqa: BLE001
        return False
    return True


# ── on or off ────────────────────────────────────────────────────

def listening(app: Any) -> bool:
    return node_state(app, NODE) == "running"


def listen(app: Any, on: bool) -> str:
    """Turn the ears on or off. "" when it happened, else why not. BLOCKS.

    Off is the default, and not only to save the model load: an app that
    opens the microphone because it launched is an app that shows a
    recording indicator nobody asked for.

    The engine consumes /sense/mic/pcm and opens no device itself, so
    the caller owns bringing `AUDIO_NODE` up around this — see
    `core.module_support.audio_driver`. Doing it here would mean the
    ears deciding whether the VOICE still needs the speaker.
    """
    return set_node(app, NODE, on)


def frame_level(msg: Any, *, samples: int = 32) -> float:
    """RMS level of one mic frame, 0..1-ish.

    Computed where the frame ARRIVES rather than on a GUI thread: a
    frame is 640 bytes and lands 100x a second, so handing every one to
    the interface to be measured puts 100 wakeups a second on the paint
    loop for a number that is one float.

    Subsampled — full precision is pointless for a bar 14 pixels tall,
    and this runs on the audio path.
    """
    data = getattr(msg, "samples", b"")
    if not data:
        return 0.0
    n = len(data) // 4
    if n == 0:
        return 0.0
    step = max(1, n // samples)
    try:
        vals = struct.unpack_from(f"<{n}f", data)[::step]
    except struct.error:
        return 0.0
    if not vals:
        return 0.0
    return math.sqrt(sum(v * v for v in vals) / len(vals))


__all__ = [
    "SLOT", "PACKAGE", "NODE", "WATCH", "TRANSCRIPT",
    "available", "frame_level", "modes", "mode", "set_mode",
    "listening", "listen", "pause", "remember_reply", "open_followup",
]
