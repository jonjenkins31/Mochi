"""The ears — how Mochi uses the STT module.

    slot: stt                jaeger-whisper-stt fills it today
    consumes  /sense/mic/pcm
    produces  /sense/stt/transcript, /sense/stt/speech_start

OPTIONAL, like the voice.

WHY THE MIC TOPIC IS LISTED HERE and not only under the audio driver:
"the agent cannot hear me" has three different causes — no audio
driver, a muted device, or an STT that is not running — and they are
indistinguishable from a log of transcripts. A surface that watches
BOTH the raw mic and the transcripts can tell them apart, so the
binding exposes both.
"""

from __future__ import annotations

import math
import struct
from typing import Any

from jaeger_os import topics

from .common import installed

SLOT = "stt"
PACKAGE = "jaeger_whisper_stt"

#: What a surface watches. The mic frame is in here on purpose — see
#: the module docstring.
WATCH = (
    topics.SENSE_MIC_PCM,            # is the microphone alive at all?
    topics.SENSE_STT_SPEECH_START,   # the VAD says you started talking
    topics.SENSE_STT_TRANSCRIPT,     # what it thinks you said
)


def available() -> bool:
    return installed(PACKAGE)


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


__all__ = ["SLOT", "PACKAGE", "WATCH", "available", "frame_level"]
