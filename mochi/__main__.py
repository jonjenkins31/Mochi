"""``python -m mochi`` — boot the app from jaeger.toml.

Nothing here builds a bus, wires a node, or opens a window. The
manifest declares all three and the framework does it; this file only
finds the manifest and blocks on the result.
"""

from __future__ import annotations

import pathlib
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    here = pathlib.Path(__file__).resolve().parent.parent
    app_dir = pathlib.Path(argv[0]) if argv else here

    manifest = app_dir / "jaeger.toml"
    if not manifest.is_file():
        print(f"no jaeger.toml at {app_dir}", file=sys.stderr)
        return 2

    from jaeger_os.app.app import JaegerApp

    app = JaegerApp(manifest)
    try:
        app.boot()
        return app.run()
    except KeyboardInterrupt:
        return 0
    finally:
        app.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
