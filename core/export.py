"""Render a show to a file — deterministically, not by recording it.

The last step: a show that plays becomes a Short you can upload.

    export(timeline, "out.mp4", size=(1080, 1920), fps=30)

DETERMINISTIC, NOT A SCREEN RECORDING. Nothing here plays in real time
or captures a window. For every frame the renderer asks "which clip is
on at t, and what does it look like `t - clip_start` into itself" — so
the result is identical on a fast machine and a slow one, and a frame
that took 300ms to compute still lands on its own 33ms slot. A capture
of a live playback would drop frames exactly when the show gets busy,
which is when it matters.

AUDIO IS MIXED, NOT SPOKEN. Dialogue is already rendered to files by
`core/dialogue.py`; this sums them into one track at their offsets. So
the same speech that scrubs in the editor is the speech in the export —
a show cannot sound different on the day.

    render_frames()  the picture, frame by frame
    mix_audio()      the sound, sample by sample
    ffmpeg           the two into an MP4

WHAT IT WILL NOT DO. It refuses to export a show whose dialogue has not
been rendered, rather than silently shipping a video with no speech in
it. `ASK` cues are improvised and have no audio by definition; they are
reported, and the export continues without them, because a rehearsal
take is not a deliverable and the operator has to know which is which.
"""

from __future__ import annotations

import array
import pathlib
import shutil
import subprocess
import wave
from typing import Any, Callable

from jaeger_os.timeline import Timeline

from core import dialogue, director

#: 9:16 at 1080. What a Short is, and the default for that reason.
VERTICAL = (1080, 1920)
FPS = 30


def available() -> bool:
    """True when there is an encoder to hand the frames to."""
    return shutil.which("ffmpeg") is not None


def active_clip(timeline: Timeline, kind: str, at_ms: int,
                target: str = "") -> Any:
    """The clip of `kind` covering `at_ms`, or None.

    LAST ONE WINS, because that is what the live display does: a new
    play command preempts whatever was showing. An export that composed
    them instead would look nothing like the rehearsal.
    """
    found = None
    for track in timeline.tracks:
        if track.kind != kind or (target and track.target != target):
            continue
        for clip in track.clips:
            end = clip.t_offset_ms + (clip.duration_ms or 10 ** 9)
            if clip.t_offset_ms <= at_ms < end:
                found = clip
    return found


class Frames:
    """Adapters, kept open between frames.

    Reopening a clip per frame would reload a model or re-decode a
    video thirty times a second, and the whole point of an offline
    render is that it can afford to be exact rather than that it can
    afford to be wasteful.
    """

    def __init__(self, size: tuple[int, int]) -> None:
        self.width, self.height = size
        self._open: dict[tuple, Any] = {}
        #: The last frame each clip produced. `next_frame()` returns
        #: None for "nothing new", not for "black" — a still image
        #: emits once and then stops — and a display HOLDS the last
        #: frame until something replaces it. A renderer that wrote
        #: black instead exported a show that was blank except for one
        #: frame per cue, which is exactly what it did.
        self._last: dict[tuple, bytes] = {}
        self._table = self._adapters()

    @staticmethod
    def _adapters() -> dict:
        """name -> adapter CLASS. The node registers instances and this
        needs one per clip: two clips sharing an adapter would have the
        second `open()` close the first, which is fine for a display
        showing one thing and wrong for a renderer holding several."""
        from jaeger_animation.node import AnimationNode

        node = AnimationNode(bus=None, width=1, height=1)
        node.register_default_adapters()
        return {name: type(instance)
                for name, instance in node._adapters.items()}  # noqa: SLF001

    def at(self, clip: Any, into_ms: int) -> bytes | None:
        """One RGBA frame, `into_ms` into `clip`."""
        payload = dict(getattr(clip, "payload", {}) or {})
        asset = str(payload.get("asset", payload.get("asset_path", "")))
        if not asset:
            return None
        key = (asset, str(sorted((payload.get("params") or {}).items())))
        adapter = self._open.get(key)
        if adapter is None:
            name = str(payload.get("adapter", "") or "auto")
            if name == "auto":
                # The ENGINE's own resolver, not a second extension
                # table — a renderer that disagreed with the display
                # about what a .json is would export a different show.
                from jaeger_animation.node import adapter_for_path

                name = adapter_for_path(asset)
            factory = self._table.get(name)
            if factory is None:
                return None
            adapter = factory()
            try:
                adapter.open(asset, width=self.width, height=self.height,
                             params=dict(payload.get("params", {})))
            except Exception:  # noqa: BLE001 — one bad clip, not a bad export
                return None
            self._open[key] = adapter
        try:
            frame = adapter.next_frame(max(0.0, into_ms / 1000.0))
        except Exception:  # noqa: BLE001
            return self._last.get(key)
        if frame is None:
            return self._last.get(key)
        data = bytes(frame.data)
        self._last[key] = data
        return data

    def close(self) -> None:
        for adapter in self._open.values():
            try:
                adapter.close()
            except Exception:  # noqa: BLE001
                pass
        self._open.clear()
        self._last.clear()


def render_frames(timeline: Timeline, out: pathlib.Path, *,
                  size: tuple[int, int] = VERTICAL, fps: int = FPS,
                  on_progress: Callable[[int, int], None] | None = None) -> int:
    """Write raw RGBA frames. Returns how many.

    One file rather than thousands of PNGs: ffmpeg reads rawvideo
    happily, and an intermediate PNG per frame is a compress and a
    decompress that nobody asked for.
    """
    width, height = size
    total_ms = director.duration_of(timeline)
    count = max(1, int(total_ms * fps / 1000))
    blank = bytes(width * height * 4)
    frames = Frames(size)
    tick = on_progress or (lambda _i, _n: None)
    written = 0
    try:
        with out.open("wb") as handle:
            for index in range(count):
                at_ms = int(index * 1000 / fps)
                clip = active_clip(timeline, "animation", at_ms)
                data = None
                if clip is not None:
                    data = frames.at(clip, at_ms - clip.t_offset_ms)
                handle.write(data if data and len(data) == len(blank)
                             else blank)
                written += 1
                if index % fps == 0:
                    tick(index, count)
    finally:
        frames.close()
    return written


def mix_audio(timeline: Timeline, out: pathlib.Path, *,
              rate: int = dialogue.SAMPLE_RATE) -> dict:
    """Sum every rendered line into one track at its own offset.

    `array` rather than numpy, for the same reason the rest of the app
    does without it. Twenty seconds is half a million samples and the
    loop below is milliseconds — an offline pass can afford the
    stdlib.
    """
    total_ms = director.duration_of(timeline)
    length = max(1, int(total_ms * rate / 1000))
    track = array.array("i", bytes(4 * length))      # 32-bit headroom
    report = {"mixed": 0, "missing": []}

    for clip, text, _voice in dialogue.lines(timeline):
        payload = clip.payload or {}
        path = payload.get("audio")
        if not path or not pathlib.Path(path).is_file():
            report["missing"].append(text[:40])
            continue
        pcm, clip_rate = dialogue.read(pathlib.Path(path))
        samples = array.array("h")
        samples.frombytes(pcm)
        start = int(clip.t_offset_ms * rate / 1000)
        # Naive resample only if the file disagrees with the mix rate;
        # normally it does not, and this costs nothing.
        step = clip_rate / rate
        for index in range(len(samples) if step == 1
                           else int(len(samples) / step)):
            position = start + index
            if position >= length:
                break
            track[position] += samples[index if step == 1
                                       else int(index * step)]
        report["mixed"] += 1

    # Clip to int16 once, at the end, so overlapping lines add properly
    # before anything is lost.
    out_pcm = array.array("h", (max(-32768, min(32767, value))
                                for value in track))
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(out_pcm.tobytes())
    return report


def export(timeline: Timeline, out: Any, *,
           size: tuple[int, int] = VERTICAL, fps: int = FPS,
           workdir: Any = None,
           on_progress: Callable[[str], None] | None = None) -> dict:
    """Picture and sound into one MP4. Returns a report.

    Refuses a show whose dialogue has not been rendered, rather than
    shipping a silent video and letting somebody find out on upload.
    """
    say = on_progress or (lambda _line: None)
    out = pathlib.Path(out)
    work = pathlib.Path(workdir or out.parent / ".export")
    work.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"out": str(out), "frames": 0, "size": size,
                             "fps": fps, "errors": []}

    written = dialogue.lines(timeline)
    if written and not dialogue.is_rendered(timeline):
        report["errors"].append(
            "dialogue is not rendered — export would be silent. "
            "Run the render pass first.")
        return report
    if not available():
        report["errors"].append("ffmpeg is not installed")
        return report

    raw, wav = work / "frames.rgba", work / "audio.wav"
    say(f"rendering {director.duration_of(timeline) / 1000:.1f}s "
        f"at {size[0]}x{size[1]} {fps}fps…")
    report["frames"] = render_frames(
        timeline, raw, size=size, fps=fps,
        on_progress=lambda i, n: say(f"  frame {i}/{n}"))
    say("mixing audio…")
    report["audio"] = mix_audio(timeline, wav)

    say("encoding…")
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", str(raw),
        "-i", str(wav),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)]
    finished = subprocess.run(command, capture_output=True, text=True)
    if finished.returncode != 0:
        report["errors"].append(finished.stderr.strip()[:400])
    else:
        report["bytes"] = out.stat().st_size if out.is_file() else 0
        say(f"wrote {out} ({report['bytes'] / 1e6:.1f} MB)")
    return report


__all__ = ["export", "render_frames", "mix_audio", "active_clip", "Frames",
           "available", "VERTICAL", "FPS"]
