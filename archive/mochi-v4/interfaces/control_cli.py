"""
Simple command-line tool to send control messages to the Mochi animation node.

The node binds a ZMQ PULL socket, so this utility connects with PUSH.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml
import zmq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CTRL_ADDR = "tcp://127.0.0.1:5556"


def _load_ctrl_address() -> str:
    """
    Look for a control address in either the root config or the animation node config.
    """
    config_candidates = [
        PROJECT_ROOT / "config.yaml",
        PROJECT_ROOT / "plugins" / "animation_node" / "config.yaml",
    ]
    for cfg_path in config_candidates:
        try:
            with cfg_path.open("r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh) or {}
        except FileNotFoundError:
            continue
        except Exception as exc:
            print(f"Warning: cannot read {cfg_path}: {exc}")
            continue

        gui_cfg = config.get("gui", {}) or {}
        node_cfg = config.get("node", {}) or {}
        ctrl_addr = (
            gui_cfg.get("ctrl_address")
            or gui_cfg.get("pub_address")  # legacy field name
            or node_cfg.get("ctrl_address")
        )
        if ctrl_addr:
            return str(ctrl_addr)
    return DEFAULT_CTRL_ADDR


def main() -> None:
    ctrl_addr = _load_ctrl_address()

    ctx = zmq.Context.instance()
    push = ctx.socket(zmq.PUSH)
    push.setsockopt(zmq.LINGER, 0)
    push.connect(ctrl_addr)
    time.sleep(0.05)  # allow the node to register our PUSH socket

    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:]).strip()
        if cmd:
            push.send_string(cmd)
            print(f"Sent: {cmd}")
        return

    print(f"Connected to Mochi control socket at {ctrl_addr}")
    print("Examples: mode demo, color 255 100 50, size 64x64, play mscripts/demo_wink.mscript")
    print("Ctrl+C to exit.")
    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue
            push.send_string(line)
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()
