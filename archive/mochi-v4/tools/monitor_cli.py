"""Simple CLI to query the Mochi host monitor REP endpoint."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

import zmq

DEFAULT_ADDR = "tcp://127.0.0.1:5560"


def query(addr: str, request: str) -> str:
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.REQ)
    sock.connect(addr)
    sock.send_string(request)
    reply = sock.recv_string()
    sock.close(0)
    return reply


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query Mochi host monitor")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to send (e.g., GET health animation)")
    parser.add_argument("-a", "--addr", default=DEFAULT_ADDR, help="REP endpoint (default: %(default)s)")
    parser.add_argument("-p", "--pretty", action="store_true", help="Pretty-print JSON replies")
    args = parser.parse_args(argv)

    cmd = " ".join(args.command).strip() or "GET health"
    try:
        reply = query(args.addr, cmd)
    except Exception as exc:
        print(f"Error querying monitor: {exc}", file=sys.stderr)
        return 1

    if args.pretty:
        try:
            obj = json.loads(reply)
            print(json.dumps(obj, indent=2, sort_keys=True))
            return 0
        except json.JSONDecodeError:
            pass
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
