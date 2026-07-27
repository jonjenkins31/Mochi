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
    p.add_argument("--nodes", action="store_true",
                   help="print what would run and where each part comes "
                        "from, then exit")
    return p.parse_args(argv)


def print_inventory() -> int:
    """Answer "what is actually running here, and whose code is it?"

    `nodes/` is empty in this project and that is correct — it holds
    node code MOCHI owns, and Mochi owns none. But "we have no nodes"
    is not what an operator sees at runtime: one is running, from an
    installed module. Rather than keep a stub file per imported node
    (a second copy of jaeger.toml that drifts), this reads live
    discovery, so it cannot be wrong.
    """
    import tomllib

    from jaeger_os.core.modules import discover_modules

    spec = tomllib.loads((PROJECT_ROOT / "jaeger.toml").read_text())
    modules = discover_modules(project_dir=PROJECT_ROOT)

    print(f"\n{spec['app']['name']} {spec['app'].get('version','')}"
          f"   bus={spec['bus']['backend']}\n")
    print(f"  {'node':12} {'slot':11} {'source':34} where")
    print("  " + "-" * 74)
    for node in spec.get("node", []):
        if not node.get("enabled", True):
            print(f"  {node['id']:12} {node.get('slot',''):11} "
                  f"{'(disabled)':34} —")
            continue
        slot = node.get("slot", "")
        if not slot:
            print(f"  {node['id']:12} {'—':11} {node.get('factory',''):34} "
                  f"this project")
            continue
        found = modules.get(slot) or []
        if not found:
            print(f"  {node['id']:12} {slot:11} "
                  f"{'!! NO MODULE FILLS THIS SLOT':34} —")
            continue
        m = found[0]
        where = "modules/ (LOCAL, shadows installed)" if m.local else "installed"
        print(f"  {node['id']:12} {slot:11} {m.module + ' ' + m.version:34} "
              f"{where}")
        print(f"  {'':12} {'':11} {str(m.source_dir)}")

    for surface in spec.get("surface", []):
        print(f"\n  surface      {surface['id']:11} {surface['factory']:34} "
              f"this project")

    print(f"\n  nodes/ holds node code THIS project owns. Empty is correct "
          f"here —\n  Mochi owns none. Copy a module into modules/ to "
          f"override one.\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse(list(sys.argv[1:] if argv is None else argv))

    if args.nodes:
        return print_inventory()

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

    from jaeger_os.app import JaegerApp

    # run() boots, starts the surfaces, and blocks on the event loop.
    # Calling boot() first double-boots and trips the single-instance
    # guard with "mochi is already running" — against itself.
    try:
        return JaegerApp(manifest).run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
