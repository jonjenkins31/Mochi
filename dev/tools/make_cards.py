"""Render a `card.png` for packs whose art is data, not a picture.

    ./venv/bin/python dev/tools/make_cards.py [--force] [pack …]

WHY THIS EXISTS. Five of Mochi's packs — bitmap man, Eric, Deborahbot
5000, both Daft Punks — contain no image file at all. Their faces are
JSON bitmap and sprite data that only the animation engine knows how to
turn into pixels. So the Cast tab drew them as empty tiles, and a
roster where half the entries are blank is worse than no roster.

The fix is not for a TAB to learn to decode bitmaps. It is to ask the
engine, once, offline, and leave the answer in the pack as `card.png` —
where `card_for()` already looks, where an author can overwrite it with
something better, and where it costs nothing at runtime.

So this boots the app exactly as the player does, plays each pack's
default expression, waits for a frame off `/act/display/frame`, and
writes it. If Mochi can show a character, this can card it.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT = pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    force = "--force" in argv
    wanted = [a for a in argv if not a.startswith("-")]

    from jaeger_os import JaegerApp, topics
    from PySide6 import QtGui, QtWidgets

    from modules import jaeger_animation as animation

    app = JaegerApp(PROJECT / "sim.toml")
    app.boot()
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    latest: list = []
    app.bus.subscribe(topics.ACT_DISPLAY_FRAME, lambda m: latest.append(m))

    written, skipped = 0, 0
    for identifier in animation.available():
        if wanted and identifier not in wanted:
            continue
        try:
            character = animation.load(identifier)
        except Exception as exc:  # noqa: BLE001
            print(f"  {identifier:<14} skipped — {exc}")
            continue
        card = pathlib.Path(character.root) / "card.png"
        if card.is_file() and not force:
            skipped += 1
            continue

        latest.clear()
        animation.play(app.bus, character, character.default_expression)
        deadline = time.time() + 4.0
        while not latest and time.time() < deadline:
            time.sleep(0.02)
        if not latest:
            print(f"  {identifier:<14} no frame in 4s — left blank")
            continue

        # The LAST frame, not the first: a blink starts on a closed eye
        # and a card of a character with its eyes shut is a bad card.
        frame = latest[-1]
        image = QtGui.QImage(
            bytes(frame.data), frame.width, frame.height,
            frame.width * 4, QtGui.QImage.Format_RGBA8888).copy()
        image.save(str(card))
        print(f"  {identifier:<14} → {card.relative_to(PROJECT)}  "
              f"({frame.width}×{frame.height})")
        written += 1

    animation.stop(app.bus)
    app.shutdown()
    print(f"\n  {written} written, {skipped} already had one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
