"""Send a single text message to the STT topic for LLM nodes to consume."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

import yaml
import zmq

from core.messages import TOPIC_STT_TEXT, build

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_CONFIG = PROJECT_ROOT / "config.yaml"


def _default_pub_address() -> str:
    try:
        with ROOT_CONFIG.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return "tcp://127.0.0.1:5557"
    broker_cfg = config.get("broker", {}) or {}
    node_cfg = config.get("node", {}) or {}
    return str(
        broker_cfg.get("backend_addr")
        or node_cfg.get("pub_backend_address")
        or "tcp://127.0.0.1:5557"
    )


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Publish text onto the STT topic.")
    parser.add_argument(
        "text",
        nargs="+",
        help="Words to send to the LLM node (combine into a single message).",
    )
    parser.add_argument(
        "--source",
        default="stt-cli",
        help="Source label stored in the message envelope.",
    )
    parser.add_argument(
        "--topic",
        default=TOPIC_STT_TEXT.decode("utf-8"),
        help="Topic to publish to (defaults to stt.text).",
    )
    parser.add_argument(
        "--pub-address",
        default=_default_pub_address(),
        help="ZeroMQ address of the broker backend (publishers connect here).",
    )
    args = parser.parse_args(argv)

    text = " ".join(args.text).strip()
    if not text:
        parser.error("No text to send.")

    topic_bytes = args.topic.encode("utf-8")
    message = build(source=args.source, kind="user", text=text)
    payload = message.to_json()

    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.LINGER, 0)
    pub.connect(args.pub_address)
    # Allow subscribers to connect before sending.
    time.sleep(0.05)
    pub.send_multipart([topic_bytes, payload])
    pub.close()


if __name__ == "__main__":
    main()
