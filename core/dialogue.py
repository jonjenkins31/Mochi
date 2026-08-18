"""Render a show's dialogue once, then treat it like any other media.

Live TTS is dispatched at its scheduled time, which is fine for a
performance and wrong for AUTHORING. Two things break:

    Timing   a SAY clip's length is a WORD-COUNT GUESS, so the
             timeline is approximate everywhere and a cue placed
             against the end of a line lands somewhere else on the day.

    Scrubbing  seeking backwards re-fires the line, so the show talks
               over itself. Nothing can un-say a sentence.

Rendering fixes both by turning a line into a FILE. A file has a real
length, so the timeline stops guessing; and a file can be played from
any offset, so scrubbing into the middle of a line is the same
operation as scrubbing into the middle of a video.

    render(timeline)  ->  every speech clip carries `audio` and a
                          TRUE duration_ms

CACHED BY CONTENT. The key is a hash of the text and the voice, so
re-rendering a show only synthesises what changed — and changing one
line does not re-cut the other twenty.

WHAT IT DELIBERATELY DOES NOT DO. It never renders `ASK`, because the
words are not written down until the model says them. An improvised
line stays live; the operator's move is to accept a take and paste it
in as a SAY, and then it renders like everything else.
"""

from __future__ import annotations

import hashlib
import pathlib
import wave
from typing import Any, Callable

from jaeger_os.timeline import Timeline

#: Where rendered lines live. Beside the project rather than beside the
#: show: two shows that use the same line should not synthesise it
#: twice, and the cache is disposable.
CACHE = pathlib.Path("render") / "dialogue"

SAMPLE_RATE = 24000          # Kokoro's, and what the wav is written at


def key_of(text: str, voice: str) -> str:
    """The cache name for one line. Content, not position — moving a
    line in the timeline must not re-synthesise it."""
    digest = hashlib.sha256(f"{voice}\x00{text}".encode()).hexdigest()
    return f"{digest[:16]}.wav"


def duration_ms(path: pathlib.Path) -> int:
    """How long a rendered line actually is."""
    try:
        with wave.open(str(path), "rb") as handle:
            return int(handle.getnframes() * 1000 / handle.getframerate())
    except Exception:  # noqa: BLE001
        return 0


def read(path: pathlib.Path) -> tuple[bytes, int]:
    """(int16 mono bytes, sample rate) — what the speaker topic wants."""
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes()), handle.getframerate()


def slice_ms(pcm: bytes, rate: int, start_ms: int) -> bytes:
    """The audio from `start_ms` onward.

    This is the whole reason for rendering: scrubbing into the middle
    of a line is a byte offset, not a re-synthesis.
    """
    offset = max(0, int(start_ms * rate / 1000)) * 2      # int16 mono
    return pcm[offset:] if offset < len(pcm) else b""


def _write(path: pathlib.Path, audio: Any, rate: int = SAMPLE_RATE) -> None:
    import numpy as np

    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def lines(timeline: Timeline) -> list[tuple[Any, str, str]]:
    """(clip, text, voice) for every speech clip worth rendering."""
    out = []
    for track in timeline.tracks:
        if track.kind != "speech":
            continue
        for clip in track.clips:
            payload = clip.payload or {}
            text = str(payload.get("text", "")).strip()
            if text:
                out.append((clip, text, str(payload.get("voice", ""))))
    return out


def render(timeline: Timeline, *, root: pathlib.Path | None = None,
           engine: Any = None, retime: bool = True,
           on_line: Callable[[str, bool], None] | None = None) -> dict:
    """Render every written line, and make the timeline tell the truth.

    `retime` rewrites each speech clip's `duration_ms` to the length of
    the audio. That is the point: a timeline whose speech durations are
    guesses cannot be cut against, and every cue placed after a line
    inherits the error.

    Returns a report rather than raising: a show with one unrenderable
    line should still render the other nineteen.
    """
    root = pathlib.Path(root or pathlib.Path.cwd())
    folder = root / CACHE
    say = on_line or (lambda _name, _hit: None)
    report = {"rendered": 0, "cached": 0, "failed": [], "moved_ms": 0}
    todo = lines(timeline)
    if not todo:
        return report

    for clip, text, voice in todo:
        path = folder / key_of(text, voice)
        if not path.is_file():
            if engine is None:
                engine = _engine(voice)
            if engine is None:
                report["failed"].append(text[:40])
                continue
            try:
                audio = engine.render(text)
                if audio is None:
                    raise ValueError("nothing to render")
                _write(path, audio)
                report["rendered"] += 1
                say(text[:40], False)
            except Exception as exc:  # noqa: BLE001
                report["failed"].append(f"{text[:40]}: {exc}")
                continue
        else:
            report["cached"] += 1
            say(text[:40], True)

        real = duration_ms(path)
        payload = dict(clip.payload or {})
        payload["audio"] = str(path)
        payload["rendered_ms"] = real
        clip.payload = payload
        if retime and real:
            report["moved_ms"] += abs(real - int(clip.duration_ms))
            clip.duration_ms = real
    return report


def _engine(voice: str) -> Any:
    """The synthesiser, or None when the module is not installed.

    Imported here rather than at module scope: rendering is an
    operator's deliberate action and loading a speech model at import
    time would make every test that touches a timeline pay for it.
    """
    try:
        from jaeger_kokoro_tts import KokoroTTS, KokoroTTSConfig
    except ImportError:
        return None
    try:
        config = KokoroTTSConfig(voice=voice) if voice else KokoroTTSConfig()
        return KokoroTTS(config)
    except Exception:  # noqa: BLE001
        try:
            return KokoroTTS()
        except Exception:  # noqa: BLE001
            return None


def is_rendered(timeline: Timeline) -> bool:
    """True when every written line has audio behind it."""
    todo = lines(timeline)
    return bool(todo) and all(
        (clip.payload or {}).get("audio") for clip, _t, _v in todo)


__all__ = ["render", "lines", "key_of", "duration_ms", "read", "slice_ms",
           "is_rendered", "CACHE", "SAMPLE_RATE"]
