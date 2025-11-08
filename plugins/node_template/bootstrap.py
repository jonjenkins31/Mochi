"""Bootstrap helpers shared by Mochi plugin nodes."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PLUGIN_ROOT.parents[1]

# Ensure the project root is available on the import path so that nodes launched
# via `python plugins/<node>/node.py` can import shared packages like `core`.
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.append(PROJECT_ROOT_STR)

def setup_logging(name: str, level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger with a consistent format."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)-8s - %(name)-18s - %(message)s"
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(level)
    logger.addHandler(handler)

    return logger

def _merge_dicts(base: dict, overlay: dict) -> dict:
    """Recursively merge dictionaries (overlay wins)."""
    merged = dict(base)
    for key, value in overlay.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged

def load_config(
    config_path: Path | None = None,
    *,
    logger: logging.Logger | None = None,
    env_var: str = "MOCHI_PLUGIN_CONFIG_JSON",
) -> dict[str, Any]:
    """Load a node configuration from YAML, applying JSON overrides."""
    config_path = config_path or (PLUGIN_ROOT / "config.yaml")
    data: dict[str, Any] = {}

    try:
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        else:
            if logger:
                logger.warning("Config file missing: %s", config_path)
    except Exception as exc:
        if logger:
            logger.error("Failed to read %s: %s", config_path, exc)

    env_raw = os.environ.get(env_var)
    if env_raw:
        try:
            env_cfg = json.loads(env_raw)
            if isinstance(env_cfg, dict):
                data = _merge_dicts(data, env_cfg)
        except json.JSONDecodeError as exc:
            if logger:
                logger.warning("Invalid %s payload: %s", env_var, exc)

    return data

def _coerce_topic(value: bytes | str, *, logger: logging.Logger | None = None) -> bytes | None:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped.encode("utf-8")
    if logger:
        logger.warning("Ignoring optional topic with unsupported type: %r", value)
    return None

def build_optional_topics(
    node_config: dict[str, Any],
    *,
    logger: logging.Logger | None = None,
    extra: Sequence[bytes | str] | None = None,
    env_var: str = "MOCHI_NODE_OPTIONAL_TOPICS",
) -> list[bytes]:
    """Collect optional topics from config, environment, and extras."""
    topics: list[bytes] = []

    for entry in node_config.get("optional_topics", []) or []:
        topic = _coerce_topic(entry, logger=logger)
        if topic:
            topics.append(topic)

    env_raw = os.environ.get(env_var, "")
    if env_raw:
        for part in env_raw.split(","):
            topic = _coerce_topic(part, logger=logger)
            if topic:
                topics.append(topic)

    if extra:
        for entry in extra:
            topic = _coerce_topic(entry, logger=logger)
            if topic:
                topics.append(topic)

    # Preserve order while removing duplicates
    seen: set[bytes] = set()
    deduped: list[bytes] = []
    for topic in topics:
        if topic not in seen:
            deduped.append(topic)
            seen.add(topic)

    return deduped
