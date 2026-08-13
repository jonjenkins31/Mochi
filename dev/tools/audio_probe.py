"""Is the speech path alive, and did the mind node break it?

    venv/bin/python dev/tools/audio_probe.py

Answers three questions in one run, because "it does not speak" has
several causes that look identical from the outside:

    1. Can this machine open an audio device at all?
    2. Does Mochi's speech path drain WITHOUT the mind node?
    3. Does it still drain WITH the mind node?

If (1) fails, it is the device or a macOS permission and nothing in
this repo will fix it. If (2) passes and (3) fails, the mind node is
the cause. If both fail, the audio_io driver is not coming up and the
chat integration is innocent.

Every device call is run on a daemon thread with a deadline: opening
audio on macOS can wedge inside CoreAudio rather than raise, and a
probe that hangs tells you nothing.
"""

from __future__ import annotations

import pathlib
import queue
import threading
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]


def bounded(label: str, fn, timeout: float = 20.0) -> bool:
    """Run fn on a thread; report OK / RAISED / HUNG. True only on OK."""
    box: dict = {}

    def run() -> None:
        try:
            fn()
            box["ok"] = True
        except BaseException as exc:  # noqa: BLE001
            box["err"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if box.get("ok"):
        print(f"  {label:34} OK")
        return True
    if "err" in box:
        print(f"  {label:34} RAISED  {box['err']}")
        return False
    print(f"  {label:34} HUNG >{timeout:.0f}s  (wedged in CoreAudio — "
          f"usually a permission never answered)")
    return False


def probe_devices() -> None:
    print("\n1. can this machine open audio at all?")

    def out_avaudio() -> None:
        from jaeger_os.core.audio.avaudio_io import OutputStream
        s = OutputStream(samplerate=24000, channels=1, dtype="float32",
                         blocksize=480, callback=lambda *a, **k: None)
        s.start(); s.stop(); s.close()

    def out_portaudio() -> None:
        import sounddevice as sd
        s = sd.OutputStream(samplerate=24000, channels=1, dtype="float32",
                            blocksize=480, callback=lambda *a, **k: None)
        s.start(); s.stop(); s.close()

    def mic() -> None:
        import sounddevice as sd
        s = sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                           blocksize=160, callback=lambda *a, **k: None)
        s.start(); s.stop(); s.close()

    bounded("speaker (avaudio)", out_avaudio)
    bounded("speaker (portaudio)", out_portaudio)
    bounded("microphone", mic)


def probe_speech(with_mind: bool, timeout: float = 90.0) -> None:
    """Boot the real manifest and ask the real TTS to say one line."""
    label = "WITH mind" if with_mind else "WITHOUT mind"
    print(f"\n{'3' if with_mind else '2'}. speech path, {label}")

    from jaeger_os.app import JaegerApp
    from jaeger_os import topics
    from modules import jaeger_kokoro_tts as tts

    app = JaegerApp(PROJECT_ROOT / "jaeger.toml")
    for node in app.spec.nodes:
        if node.id == "mind":
            node.enabled = with_mind
    if with_mind:
        from modules import jaeger_agent as mind
        mind.chat_only()
        mind.resolve_model(app.spec.inline_config.setdefault("mind", {}))

    spoken: queue.Queue = queue.Queue()
    app.boot()
    time.sleep(2)
    states = {n["id"]: n["state"] for n in app.supervisor.ls()}
    print(f"  audio_io state: {states.get('audio_io', '(absent)')}"
          f"   tts: {states.get('tts', '(absent)')}")

    app.bus.subscribe(topics.ACT_SPEECH_SPOKEN, spoken.put)
    tts.say(app.bus, "Testing the speech path, one two three.")
    try:
        ack = spoken.get(timeout=timeout)
        verdict = "SPOKE" if ack.ok else f"SILENT — {ack.reason}"
        print(f"  {verdict}   ({ack.duration_s:.1f}s)")
    except queue.Empty:
        print(f"  no done-ack within {timeout:.0f}s")
    app.shutdown()


if __name__ == "__main__":
    probe_devices()
    probe_speech(with_mind=False)
    probe_speech(with_mind=True)
    print("\nread it as:")
    print("  1 fails            → device/permission, not this repo")
    print("  2 passes, 3 fails  → the mind node is the cause")
    print("  2 and 3 both fail  → audio_io is not coming up; chat is innocent")
