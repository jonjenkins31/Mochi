"""The voice — how Mochi uses the TTS module.

    slot: tts                jaeger-kokoro-tts fills it today
    consumes  /act/speech/say, /act/speech/stop, /act/speaker/state
    produces  /act/speech/spoken, /act/speech/chunk,
              /act/speaker/pcm, /act/speaker/stop

OPTIONAL. A character with no voice is still a character — that is
exactly what v5.0 was — so nothing here raises when the module is
absent. `installed()` is what the UI asks before promising anything.

TO SWAP ENGINES, change nothing here. The manifest binds `slot = "tts"`
and whichever module claims it fills the slot; Piper instead of Kokoro
is an install, not an edit. This file only changes if MOCHI wants to
use the voice differently.
"""

from __future__ import annotations

from typing import Any

from jaeger_os import topics

from .common import installed

SLOT = "tts"

#: The package that fills the slot today. Named ONLY to answer "is a
#: voice available" — nothing here imports it, so swapping engines
#: does not break this file, it just makes this check wrong until
#: someone updates it.
PACKAGE = "jaeger_kokoro_tts"

#: Topics a surface watches to follow the speech path.
WATCH = (
    topics.ACT_SPEECH_SAY,       # what was asked for
    topics.ACT_SPEECH_SPOKEN,    # the done-ack: ok, duration, reason
    topics.ACT_SPEECH_CHUNK,     # per-chunk AMPLITUDE — the lip-sync signal
    topics.ACT_SPEAKER_STATE,    # the device: playing or idle
)


def available() -> bool:
    return installed(PACKAGE)


def say(bus: Any, text: str) -> None:
    """Ask for speech. The same topic a mind uses in v5.2 — driving it
    by hand now is how you find the wiring works before there is
    anything else to blame."""
    text = (text or "").strip()
    if text:
        bus.publish(topics.SpeechCommand(text=text))


def stop(bus: Any) -> None:
    """Barge-in — TWO topics, deliberately.

    SpeechStop tells the engine to stop SYNTHESISING; SpeakerStop tells
    the driver to drop what is already queued at the device. Either
    alone leaves half a sentence playing, which is the half-second that
    makes an assistant feel deaf when you talk over it.
    """
    bus.publish(topics.SpeechStop())
    bus.publish(topics.SpeakerStop())


__all__ = ["SLOT", "PACKAGE", "WATCH", "available", "say", "stop"]
