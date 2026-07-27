"""Mochi — a virtual character you can run.

    jaeger.toml → InProcBus → animation module → /act/display/frame → window

Run:
    python3 main.py                  # the player
    python3 main.py --character NAME # a different pack
    python3 main.py --asset FILE     # play any file instead

Same shape as JP01-CC01's launcher on purpose: a thin main() that
parses flags and sets env overrides the factories read, then hands
everything to ``JaegerApp(PROJECT_ROOT).run()``. The chassis owns the
bus, the supervisor, the Qt application, signal handling and teardown.
Two apps built the same way is what makes it a standard rather than a
one-off.

Mochi owns NO engine code. The face comes from whichever module fills
the `animation` slot — see jaeger.toml. This file never imports it.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mochi", description="Play a character.")
    p.add_argument("--character", metavar="NAME",
                   help="character pack to load (default: from config.yaml)")
    p.add_argument("--asset", metavar="FILE",
                   help="play this file instead of a character — gif, png, "
                        "mp4, or mscript. The adapter is chosen by extension.")
    p.add_argument("--scale", type=int, metavar="N",
                   help="window zoom (default: from config.yaml)")
    p.add_argument("--no-cycle", action="store_true",
                   help="hold the default expression instead of walking them")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(list(sys.argv[1:] if argv is None else argv))

    # Flags reach the surface factory as env overrides rather than
    # globals — the same trick JP01 uses, and the reason the factory
    # stays a plain (app, spec) callable the chassis can build.
    if args.character:
        os.environ["MOCHI_CHARACTER"] = args.character
    if args.asset:
        asset = pathlib.Path(args.asset).expanduser().resolve()
        if not asset.is_file():
            print(f"no such asset: {asset}", file=sys.stderr)
            return 2
        os.environ["MOCHI_ASSET"] = str(asset)
    if args.scale:
        os.environ["MOCHI_SCALE"] = str(args.scale)
    if args.no_cycle:
        os.environ["MOCHI_NO_CYCLE"] = "1"

    manifest = PROJECT_ROOT / "jaeger.toml"
    if not manifest.is_file():
        print(f"no jaeger.toml at {PROJECT_ROOT}", file=sys.stderr)
        return 2

    from jaeger_os.app.app import JaegerApp

    # run() boots, starts the surfaces, and blocks on the event loop.
    # Calling boot() first double-boots and trips the single-instance
    # guard with "mochi is already running" — against itself.
    try:
        return JaegerApp(manifest).run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
