# A tiny XPUB/XSUB proxy so publishers and subscribers stay decoupled.
# Frontend (XPUB) -> subscribers connect
# Backend  (XSUB) -> publishers connect

from __future__ import annotations

import os
import sys

import zmq

DEFAULT_XPUB = "tcp://127.0.0.1:5555"
DEFAULT_XSUB = "tcp://127.0.0.1:5557"


def _resolve_endpoints(argv: list[str]) -> tuple[str, str]:
    """
    Resolve XPUB/XSUB addresses from CLI arguments or environment variables.
    """
    xpub = argv[0] if len(argv) >= 1 else os.environ.get("MOCHI_BROKER_XPUB", DEFAULT_XPUB)
    xsub = argv[1] if len(argv) >= 2 else os.environ.get("MOCHI_BROKER_XSUB", DEFAULT_XSUB)
    return xpub, xsub


def main() -> None:
    xpub_addr, xsub_addr = _resolve_endpoints(sys.argv[1:])

    ctx = zmq.Context.instance()
    xpub = ctx.socket(zmq.XPUB)
    xpub.bind(xpub_addr)
    xsub = ctx.socket(zmq.XSUB)
    xsub.bind(xsub_addr)

    print(f"[broker] XPUB {xpub_addr}  XSUB {xsub_addr}")
    try:
        zmq.proxy(xsub, xpub)  # forward both ways
    except KeyboardInterrupt:
        pass
    finally:
        xpub.close()
        xsub.close()
        ctx.term()


if __name__ == "__main__":
    main()
