"""Voice pipelines you can switch between on real hardware.

Testing pipelines against a real microphone in a real room is what Mochi
is FOR, so the voice loop is not one wiring with a few knobs — it is a
named set of whole compositions, and swapping between them is a choice
in the Chat tab.

Two ship today, both taken from the reference scripts in the project
root, which are the versions that actually work:

    assistant   voice_assistant.py — half duplex. A wake phrase opens a
                turn, the microphone is PAUSED while the character
                talks, and a follow-up window lets you keep going
                without saying the wake phrase again. Needs nothing
                beyond the modules themselves.

    chat        voice_chat.py — full duplex. No wake phrase, every
                phrase is a turn, and you can talk over the reply
                (barge-in). Needs an echo canceller, because the
                microphone is live while the speaker is playing.

WHY THIS FILE EXISTS AND WHY IT IS SETTINGS, NOT CODE. Every value below
is a real field of the engine modules' own config — this composes them,
it does not reimplement them. A third mode is a dict, not a subclass.

WHAT WAS ACTUALLY BROKEN. Neither of the engine's two self-speech
defences was switched on: `require_wake_word` sat at its dataclass
default of False, and `self_speech_filter` was on but inert because
nothing ever called `remember_reply()`. With a live mic, no echo
canceller and no wake phrase, the character heard its own reply,
answered it, heard THAT, and looped. Both defences are configured here;
the microphone pause that makes `assistant` airtight is applied by the
Chat tab, which is the thing that knows when we are speaking.
"""

from __future__ import annotations

from typing import Any

from core.module_support import installed

#: Whisper mishears a name it has never been trained on, so a wake
#: phrase is a small phonetic family rather than one spelling. Straight
#: off voice_assistant.py's `_ASSISTANT_NAMES`, retargeted at Mochi.
WAKE_PHRASES = [
    f"{prefix} {name}"
    for prefix in ("ok", "okay", "hey")
    for name in ("mochi", "mochee", "motchi", "moshi")
]

#: The echo canceller `chat` needs. Absent by default on macOS, and its
#: absence is the difference between barge-in and a feedback loop.
AEC_PACKAGE = "speexdsp"

MODES: dict[str, dict[str, Any]] = {
    "assistant": {
        "what": "half duplex — wake phrase, mic paused while speaking",
        # Mochi-side, applied by the Chat tab.
        "pause_mic_while_speaking": True,
        # How long after the speaker drains before the ears reopen. The
        # VAD's own hangover is 700ms and it pads 250ms more, so a phrase
        # closing right after playback can still hold the reply's tail.
        "reopen_after_s": 1.0,
        "stt": {
            # The reference's own pipeline: base.en gates every phrase
            # cheaply, medium.en only re-decodes what got past the wake.
            "stt_mode": "two_pass",
            "fast_model_name": "base.en",
            "accurate_model_name": "medium.en",
            "require_wake_word": True,
            "wake_phrases": WAKE_PHRASES,
            "wake_match_threshold": 0.78,
            "followup_window_s": 10.0,
            # Off: the mic is paused while we talk, so there is nothing
            # to barge in on, and a live barge-in path would only give
            # the speaker a way back into the VAD.
            "barge_in": False,
            "self_speech_filter": True,
            "self_speech_threshold": 0.75,
            "llm_gate": False,
            "max_speech_ms": 8000,
        },
        "audio_io": {"aec": False},
    },
    "chat": {
        "what": "full duplex — no wake phrase, barge-in, needs an echo canceller",
        # The mic stays live; the echo canceller is what keeps the reply
        # out of it. Pausing here would remove barge-in, which is the
        # whole point of this mode.
        "pause_mic_while_speaking": False,
        "reopen_after_s": 0.0,
        "stt": {
            "stt_mode": "two_pass",
            "fast_model_name": "base.en",
            "accurate_model_name": "medium.en",
            "require_wake_word": False,
            "wake_phrases": [],
            "barge_in": True,
            "self_speech_filter": True,
            "self_speech_threshold": 0.75,
            "llm_gate": False,
            # voice_chat.py lets a turn run longer — you are having a
            # conversation, not issuing a command.
            "max_speech_ms": 12000,
        },
        "audio_io": {"aec": True},
    },
}

DEFAULT = "assistant"


def names() -> tuple[str, ...]:
    return tuple(MODES)


def describe(name: str) -> str:
    return str(MODES.get(name, {}).get("what", ""))


def _config(app: Any) -> dict:
    """The live settings mapping, from a booted app or from a raw one.

    main() applies a mode BEFORE the app boots, when all that exists is
    the manifest's parsed `[config.*]` tables; the Chat tab applies one
    after, when the same tables hang off `app.config`. Accepting both
    keeps one apply() instead of two that can disagree.
    """
    config = getattr(app, "config", None)
    if isinstance(config, dict):
        return config
    return app if isinstance(app, dict) else {}


def current(app: Any) -> str:
    """Which pipeline the manifest, or the last switch, selected."""
    chosen = str((_config(app).get("voice") or {}).get("mode", ""))
    return chosen if chosen in MODES else DEFAULT


def setting(app: Any, key: str, fallback: Any = None) -> Any:
    """One of the current mode's Mochi-side behaviours."""
    return MODES[current(app)].get(key, fallback)


def warning(name: str) -> str:
    """What this mode cannot do on this machine, or "".

    `chat` keeps a live microphone next to a playing speaker and trusts
    an echo canceller to tell them apart. Without one it does not
    degrade politely — it feeds the reply straight back in, which is
    exactly the loop the wake phrase was hiding.
    """
    if name == "chat" and not installed(AEC_PACKAGE):
        return (f"no echo canceller ({AEC_PACKAGE}) — the mic will hear the "
                f"reply. `pip install {AEC_PACKAGE}`, or use assistant mode.")
    return ""


def apply(app: Any, name: str) -> None:
    """Write a mode's settings into the live config slices.

    Writing only. Both nodes read their config when they are BUILT, so
    the caller restarts whatever is running — see
    `modules.jaeger_whisper_stt.set_mode` for the same shape and the
    same reason.
    """
    if name not in MODES:
        return
    config = _config(app)
    config.setdefault("voice", {})["mode"] = name
    for key in ("stt", "audio_io"):
        config.setdefault(key, {}).update(MODES[name][key])


__all__ = [
    "MODES", "DEFAULT", "WAKE_PHRASES", "AEC_PACKAGE",
    "names", "describe", "current", "setting", "warning", "apply",
]
