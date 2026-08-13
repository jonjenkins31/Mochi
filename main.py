"""Mochi — a virtual character you can run.

    jaeger.toml → InProcBus → animation module → /act/display/frame → window

Run:
    python3 main.py                  # the player
    python3 main.py sim              # sim.toml — no audio hardware
    python3 main.py --nodes          # what would run, and from where
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
    p.add_argument("variant", nargs="?", default="jaeger", metavar="VARIANT",
                   help="which manifest to bring up: a name (sim -> "
                        "sim.toml) or a path. Default: jaeger.toml")
    p.add_argument("--character", metavar="NAME",
                   help="character pack to load (default: from the manifest)")
    p.add_argument("--asset", metavar="FILE",
                   help="play this file instead of a character — gif, png, "
                        "mp4, or mscript. The adapter is chosen by extension.")
    p.add_argument("--scale", type=int, metavar="N",
                   help="window zoom (default: from the manifest)")
    p.add_argument("--no-cycle", action="store_true",
                   help="hold the default expression instead of walking them")
    p.add_argument("--nodes", action="store_true",
                   help="print what would run and where each part comes "
                        "from, then exit")
    return p.parse_args(argv)


def resolve_manifest(variant: str) -> pathlib.Path | None:
    """Which manifest to bring up.

    A NAME resolves to ``<name>.toml`` in the project root; a path is
    taken as given. Same shape as `ros2 launch <pkg> <file>`: one
    launcher, the composition varies.

    The point of separate manifests rather than flags: a variant that
    only changes a SETTING is a flag, but one that changes which NODES
    exist is not. A sim build wants a fake motor and no serial link —
    not the same nodes with a boolean.
    """
    candidate = pathlib.Path(variant)
    if candidate.suffix == ".toml" or candidate.is_absolute():
        manifest = (candidate if candidate.is_absolute()
                    else PROJECT_ROOT / candidate)
    else:
        manifest = PROJECT_ROOT / f"{variant}.toml"

    if manifest.is_file():
        return manifest

    available = sorted(p.stem for p in PROJECT_ROOT.glob("*.toml"))
    print(f"no manifest at {manifest}", file=sys.stderr)
    if available:
        print(f"available: {', '.join(available)}", file=sys.stderr)
    return None


def print_inventory(manifest: pathlib.Path) -> int:
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

    spec = tomllib.loads(manifest.read_text())
    modules = discover_modules(project_dir=PROJECT_ROOT)

    print(f"\n{spec['app']['name']} {spec['app'].get('version','')}"
          f"   bus={spec['bus']['backend']}   ({manifest.name})\n")
    print(f"  {'node':12} {'slot':11} {'source':34} where")
    print("  " + "-" * 74)
    for node in spec.get("node", []):
        # `enabled = false` is DECLARED BUT NOT STARTED, not "absent" —
        # the audio nodes live that way so a text-only launch opens no
        # device, and printing "(disabled)" instead of the module that
        # would fill the slot hid the answer to "what runs if I switch
        # the mic on?".
        boot = "" if node.get("enabled", True) else "   · off at boot"
        slot = node.get("slot", "")
        if not slot:
            print(f"  {node['id']:12} {'—':11} {node.get('factory',''):34} "
                  f"this project{boot}")
            continue
        found = modules.get(slot) or []
        if not found:
            hint = node.get("package", "")
            print(f"  {node['id']:12} {slot:11} "
                  f"{'not installed':34} "
                  + (f"pip install {hint}" if hint else "—"))
            continue
        m = found[0]
        where = ("modules/ (LOCAL, shadows installed)" if m.local
                 else "installed") + boot
        label = (m.name or m.module) + " " + m.version
        print(f"  {node['id']:12} {slot:11} {label:34} "
              f"{where}")
        identity = f"{m.id} · {m.implementation}" if m.id else m.module
        print(f"  {'':12} {'':11} {identity}")
        print(f"  {'':12} {'':11} {str(m.source_dir)}")

    for surface in spec.get("surface", []):
        print(f"\n  surface      {surface['id']:11} {surface['factory']:34} "
              f"this project")

    print(f"\n  nodes/ holds node code THIS project owns. Empty is correct "
          f"here —\n  Mochi owns none. Copy a module into modules/ to "
          f"override one.\n")
    return 0


def _wants_tools(manifest: pathlib.Path) -> bool:
    """Does `[config.mind] tools` ask for the full agent?

    Read with tomllib rather than through the framework because the
    answer is needed BEFORE jaeger_os is imported — see main(). Default
    False: a desk character wants conversation, and ~96 tool schemas are
    ~15,000 tokens against this manifest's 4096-token window.
    """
    import tomllib

    try:
        spec = tomllib.loads(manifest.read_text())
    except Exception:  # noqa: BLE001 — the chassis reports a bad manifest
        return False
    return bool(((spec.get("config") or {}).get("mind") or {}).get("tools", False))


def main(argv: list[str] | None = None) -> int:
    args = _parse(list(sys.argv[1:] if argv is None else argv))

    manifest = resolve_manifest(args.variant)
    if manifest is None:
        return 2

    # Mochi wants a chatbot, not an agent — but that is a SETTING, not a
    # limit built into the app, so it is read from the manifest like
    # every other composition decision. `tomllib` and not the framework's
    # parser on purpose: this has to be decided before jaeger_os is
    # imported at all, because discovery imports every installed module
    # to read its manifest and jaeger-agent registers its ~96 tools at
    # import time. By the time a node boots it is far too late.
    from modules import jaeger_agent as mind
    mind.chat_only(not _wants_tools(manifest))

    if args.nodes:
        return print_inventory(manifest)

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

    from jaeger_os.app import JaegerApp

    # run() boots, starts the surfaces, and blocks on the event loop.
    # Calling boot() first double-boots and trips the single-instance
    # guard with "mochi is already running" — against itself.
    try:
        app = JaegerApp(manifest)
        # Constructing parses the manifest without booting, which is the
        # only window in which a blank `model_path` can still be filled
        # in: the mind node reads its config once, at setup.
        mind.resolve_model(app.spec.inline_config.setdefault("mind", {}))
        # The selected voice pipeline decides the ears' and the driver's
        # settings, and both read them when they are BUILT. Applying it
        # here rather than from the Chat tab means the manifest's choice
        # holds for any surface, and for a node started before a window
        # exists.
        from core import voice_modes

        voice_modes.apply(app.spec.inline_config,
                          voice_modes.current(app.spec.inline_config))
        return app.run()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
