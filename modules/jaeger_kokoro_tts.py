"""The voice — how Mochi uses the TTS module.

    slot: tts                jaeger-kokoro-tts fills it today
    consumes  /act/speech/say, /act/speech/stop, /act/speaker/state
    produces  /act/speech/spoken, /act/speech/chunk,
              /act/speaker/pcm, /act/speaker/stop

OPTIONAL. A character with no voice is still a character — that is
exactly what v5.0 was — so nothing here raises when the module is
absent. `installed()` is what the UI asks before promising anything.

This integration deliberately carries Kokoro's real import name. If Mochi
imports a different TTS module later, give that provider its own explicitly
named integration file and update the Interface import so operators can see
which module is in use.
"""

from __future__ import annotations

import re
from typing import Any

from jaeger_os import topics

from core.module_support import (
    config_of, installed, node_state, set_node, settings)

SLOT = "tts"

#: The exact import package integrated by this module file.
PACKAGE = "jaeger_kokoro_tts"

#: The node id jaeger.toml gives this slot — what the supervisor answers to.
NODE = "tts"

#: The device, not the engine: "playing" or "idle". Named on its own
#: because it is what a surface watches to know when the character's
#: voice is in the room — which is exactly when the microphone must not
#: be listening. Synthesis finishing and audio finishing are different
#: events, and only this one tracks the speaker.
SPEAKER = topics.ACT_SPEAKER_STATE

#: The done-ack: ok, duration_s, reason. Named on its own because a
#: surface that asks for speech as a SIDE EFFECT — the Chat tab
#: speaking a reply — has no other way to find out it did not happen.
#: Synthesis succeeding and audio playing are two different events, and
#: only this one knows the difference.
SPOKEN = topics.ACT_SPEECH_SPOKEN

#: Topics a surface watches to follow the speech path.
WATCH = (
    topics.ACT_SPEECH_SAY,       # what was asked for
    topics.ACT_SPEECH_SPOKEN,    # the done-ack: ok, duration, reason
    topics.ACT_SPEECH_CHUNK,     # per-chunk AMPLITUDE — the lip-sync signal
    topics.ACT_SPEAKER_STATE,    # the device: playing or idle
)


def available() -> bool:
    return installed(PACKAGE)


#: Anything a language model writes for a READER and a listener cannot
#: hear. Kokoro does not silently skip these — it pronounces what it can
#: and stumbles on the rest, so "Hello! 😊" is read aloud with a noise
#: where the emoji is, and a bulleted list becomes "dash dash dash".
#: Both reference pipelines (`voice_assistant.py`, `voice_chat.py`) clean
#: the text before synthesis; this is that function, at the one place
#: every spoken string in Mochi passes through.
_SPOKEN_NOISE = (
    (re.compile(r"```.*?```", re.DOTALL), " "),   # fenced code
    (re.compile(r"`([^`]*)`"), r"\1"),            # inline code
    (re.compile(r"\*+"), ""),                     # bold / italic marks
    (re.compile(r"^\s*[-*•]\s+", re.M), ""),   # bullets
    (re.compile(r"^\s*\d+[.)]\s+", re.M), ""),    # numbered lists
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),  # [text](link)
    (re.compile(r"#+\s*"), ""),                   # headings
)

#: Emoji, pictographs, dingbats, flags, and the variation selector and
#: zero-width joiner that glue them together. A range rather than a list
#: because a model will reach for one nobody thought to enumerate.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF"     # pictographs, emoticons, symbols
    "\U00002600-\U000027BF"      # misc symbols + dingbats
    "\U0001F1E6-\U0001F1FF"      # regional indicators (flags)
    "\U0000FE00-\U0000FE0F"      # variation selectors
    "\U00002190-\U000021FF"      # arrows
    "\U00002B00-\U00002BFF"      # more arrows and shapes
    "\U0000200D]+"               # zero-width joiner
)


def speakable(text: str) -> str:
    """Strip what a listener cannot hear: markdown, emoji, list marks.

    Punctuation is left alone — Kokoro uses it for prosody, and a reply
    read without its commas sounds like one long word.
    """
    text = _EMOJI.sub(" ", text or "")
    for pattern, replacement in _SPOKEN_NOISE:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def say(bus: Any, text: str, *, voice: str = "") -> None:
    """Ask the configured TTS module to speak over its bus contract.

    Cleaned on the way out, HERE rather than at each caller, because
    every spoken string in the app goes through this one function and a
    caller that forgot would be a caller that reads emoji aloud.

    `voice` rides the REQUEST rather than the node's config, which is
    why choosing one costs nothing: the alternative is a restart, and
    Kokoro's restart reloads 82M parameters to change a string. Empty
    means the module's own default.
    """
    text = speakable(text)
    if text:
        bus.publish(topics.SpeechCommand(text=text, voice=voice))


# ── which voice ──────────────────────────────────────────────────
#
# Kokoro has ONE synthesis path — unlike the ears, there is no pipeline
# to choose between. What varies is the voice, so that is what the tabs
# offer.

def voices() -> tuple[tuple[str, str], ...]:
    """(voice id, what it sounds like) — the module's own curated list.

    Kokoro ships no introspection API, so the module keeps a list and
    accepts any id anyway. Reading its list rather than copying one here
    means a voice it adds shows up without an edit in Mochi.
    """
    if not available():
        return ()
    try:
        from jaeger_kokoro_tts.cli import VOICES
    except Exception:  # noqa: BLE001 — a broken engine must not kill a tab
        return ()
    return tuple((vid, f"{region.lower()} · {desc}")
                 for region, rows in VOICES.items() for vid, desc in rows)


def voice(app: Any) -> str:
    """Which voice Mochi speaks in. Empty = the module's own default."""
    return str(settings(app, NODE).get("voice", ""))


def set_voice(app: Any, name: str) -> None:
    """Choose the voice — for the Voice tab and for spoken chat replies.

    The manifest's config slice, because it needs to be somewhere BOTH
    tabs read and the manifest already is that place. No restart: the id
    rides each request, and a node rebuilt later reads the same key.
    """
    config_of(app).setdefault(NODE, {})["voice"] = name


# ── on or off ────────────────────────────────────────────────────

def audible(app: Any) -> bool:
    return node_state(app, NODE) == "running"


def enable(app: Any, on: bool) -> str:
    """Turn the voice on or off. "" when it happened, else why not. BLOCKS.

    Off is the default: a character that talks out loud the first time
    you type is a surprise, not a feature — and warming Kokoro costs ~8s
    and a model load that a text conversation never needs.

    Kokoro publishes PCM to /act/speaker/pcm and drives no device, so
    the caller owns bringing `AUDIO_NODE` up around this — see
    `core.module_support.audio_driver`. Without a driver, synthesis
    succeeds into silence.
    """
    return set_node(app, NODE, on)


def stop(bus: Any) -> None:
    """Barge-in — TWO topics, deliberately.

    SpeechStop tells the engine to stop SYNTHESISING; SpeakerStop tells
    the driver to drop what is already queued at the device. Either
    alone leaves half a sentence playing, which is the half-second that
    makes an assistant feel deaf when you talk over it.
    """
    bus.publish(topics.SpeechStop())
    bus.publish(topics.SpeakerStop())


__all__ = [
    "SLOT", "PACKAGE", "NODE", "WATCH", "SPOKEN", "SPEAKER",
    "available", "say", "stop", "voices", "voice", "set_voice",
    "audible", "enable",
]
