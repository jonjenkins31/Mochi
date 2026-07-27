"""Package entry point — lets you run jaeger as `python -m mochi`.

Equivalent to `python -m mochi.main`. Delegates to `main.main()`
which routes to either CLI chat (default) or the voice loop daemon
(when `--voice` is passed). See `python -m mochi --help` and
`python -m mochi --voice --help`.
"""

from __future__ import annotations

from .main import main


if __name__ == "__main__":
    raise SystemExit(main())
