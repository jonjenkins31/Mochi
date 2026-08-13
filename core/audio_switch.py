"""Turning the ears and the voice on, from whichever tab you are in.

Three nodes, two switches, one shared device:

    ears   stt  ─┐
                 ├─▶ audio_io   the driver, and the only thing that
    voice  tts  ─┘               opens a microphone or a speaker

The ears and the voice are independent — you can run the STT to watch
transcripts with no voice, or the TTS to try a Kokoro voice with no
microphone in the room. What is NOT independent is the driver they
share: it has to be running while either one is, it has to be CAPTURING
only while the ears are, and both of those are read when it is built.
So the two switches cannot each own it, and neither can a tab.

That is what this file is. Every switch anywhere in the app comes
through `switch()`, and every switch anywhere reads its position back
from `state()` — which asks the supervisor what is actually running
rather than remembering what was clicked. Three tabs can therefore show
the same switch without any of them telling the others anything, and
without the three of them ever disagreeing.

POWER IS NOT ROUTING. Running the ears is a different question from
whether what they hear should be answered by the mind. This file only
does power; the Chat tab owns the routing, which is why turning the
microphone on there no longer implies a conversation.
"""

from __future__ import annotations

from typing import Any

from core.module_support import audio_driver, node_state
from modules import jaeger_kokoro_tts as tts
from modules import jaeger_whisper_stt as stt


def state(app: Any) -> tuple[bool, bool]:
    """(ears, voice) — what the supervisor is ACTUALLY running."""
    return stt.listening(app), tts.audible(app)


def available(app: Any) -> tuple[bool, bool]:
    """(ears, voice) — whether each can be switched on at all.

    A switch needs both a module installed to run and a node declared to
    run it in. sim.toml declares no audio, so there is nothing to start
    and the box says so by staying grey.
    """
    return (stt.available() and node_state(app, stt.NODE) != "",
            tts.available() and node_state(app, tts.NODE) != "")


def switch(app: Any, *, ears: bool | None = None, voice: bool | None = None,
           restart: bool = False) -> str:
    """Move the audio stack to the asked-for shape. "" or why not.

    `None` means "leave that one alone", so a tab that owns one switch
    never has to know the position of the other — it passes its own and
    the current state supplies the rest.

    BLOCKS: starting the ears loads a Whisper model and opening the
    device is 3.6s on macOS. Call it off the GUI thread.

    Order matters both ways. An engine started before the driver hears
    or plays nothing; a driver stopped before its engine drops audio
    mid-sentence. `restart` is for a pipeline change, where every node
    has to be rebuilt to read new settings and "start what is already
    running" is a no-op.
    """
    live_ears, live_voice = state(app)
    ears = live_ears if ears is None else bool(ears)
    voice = live_voice if voice is None else bool(voice)

    failed = ""
    if restart or not ears:
        failed = stt.listen(app, False) or failed
    if restart or not voice:
        failed = tts.enable(app, False) or failed
    if restart:
        # The driver's own settings — the echo canceller — belong to a
        # pipeline too, and it also only reads them when it is built.
        failed = audio_driver(app, capture=False, wanted=False) or failed
    # Capture follows the EARS alone: a driver that opens the microphone
    # so that a reply can be spoken puts a recording indicator in the
    # menu bar for the one job that never needed one.
    failed = audio_driver(app, capture=ears, wanted=ears or voice) or failed
    if ears:
        failed = stt.listen(app, True) or failed
    if voice:
        failed = tts.enable(app, True) or failed
    return failed


__all__ = ["state", "available", "switch"]
