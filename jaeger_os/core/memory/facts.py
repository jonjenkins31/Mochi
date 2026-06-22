"""Per-instance facts store — Lilith's memory layer.

Ported from :mod:`jaeger_os.core.memory.memory` (phase 2b) and simplified for
Lilith's single-instance assumption during phase 2. Persists key/value
facts to JSON at ``<instance>/memory/facts.json`` with atomic writes
and in-process threading lock. fcntl cross-process locking and the
embedded semantic-search layer are deferred (phase 3).

Tools that wrap these primitives live in :mod:`lilith.agent.tools`
(``remember`` / ``recall`` / ``forget`` / ``list_facts``) and register
through pydantic-ai via :mod:`lilith.main`.

Storage shape on disk:

    {
      "schema_version": 1,
      "facts": {
        "favorite_color": "teal",
        "preferred_video_length_seconds": "90"
      }
    }

The schema version lets us evolve later without breaking existing
instances. Reads tolerate the older flat-dict shape (jaeger's
"loose" form) too — same forgiveness as jaeger.core.memory.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


# Single-instance assumption for phase 2. The default lilith instance
# dir is colocated with the package, mirroring jaeger's pattern; a
# future instance loader (phase 3 work) will swap this for a runtime
# resolution from ``LILITH_INSTANCE_DIR`` env var + manifest.
_DEFAULT_INSTANCE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "instance" / "default"
)


_lock = threading.Lock()


def _facts_path(instance_dir: Path | None = None) -> Path:
    """Resolve the facts.json path for the active instance."""
    target = instance_dir or _DEFAULT_INSTANCE_DIR
    return target / "memory" / "facts.json"


def _read_facts_raw(instance_dir: Path | None = None) -> dict[str, str]:
    """Read the facts dict. Returns {} on missing file or malformed JSON
    so first-use never crashes."""
    path = _facts_path(instance_dir)
    if not path.exists():
        return {}
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    if "schema_version" in data and isinstance(data.get("facts"), dict):
        return {k: str(v) for k, v in data["facts"].items() if isinstance(k, str)}
    # Tolerate flat dict (jaeger's "loose" form) — strip private keys.
    return {
        k: str(v) for k, v in data.items()
        if isinstance(k, str) and not k.startswith("_")
    }


def _write_facts_atomic(
    facts: dict[str, str], instance_dir: Path | None = None,
) -> None:
    """Atomic write — temp file + fsync + os.replace. Same shape as
    jaeger.core.memory._write_facts_atomic."""
    path = _facts_path(instance_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": SCHEMA_VERSION, "facts": dict(facts)}
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=".facts.", suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=True, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "my", "the", "a", "an", "is", "of", "do", "i", "what",
    "this", "that", "was", "were", "are",
}


def remember(key: str, value: str, instance_dir: Path | None = None) -> None:
    """Persist ``value`` under ``key``. Overwrites if the key already
    existed. In-process safe via the module-level threading.Lock."""
    with _lock:
        facts = _read_facts_raw(instance_dir)
        facts[str(key).strip()] = str(value)
        _write_facts_atomic(facts, instance_dir)


def recall(key: str, instance_dir: Path | None = None) -> str | None:
    """Look up a fact. Exact-match first, then fuzzy match by word
    overlap (skipping stopwords) so the LLM's natural-language key
    ("favorite color") finds the stored snake_case key
    ("favorite_color")."""
    with _lock:
        facts = _read_facts_raw(instance_dir)
    if not facts:
        return None
    if key in facts:
        return facts[key]
    needle = key.lower().strip()
    needle_alt = needle.replace(" ", "_")
    for stored_key, stored_val in facts.items():
        normalized = stored_key.lower().replace("_", " ")
        if needle in normalized or needle_alt in stored_key.lower():
            return stored_val
    needle_words = {w for w in _WORD_RE.findall(needle) if w not in _STOPWORDS}
    if not needle_words:
        return None
    best_key, best = None, 0
    for stored_key in facts:
        stored_words = {
            w for w in _WORD_RE.findall(stored_key.lower().replace("_", " "))
            if w not in _STOPWORDS
        }
        overlap = len(needle_words & stored_words)
        if overlap > best:
            best, best_key = overlap, stored_key
    return facts[best_key] if best_key and best >= 1 else None


def forget(key: str, instance_dir: Path | None = None) -> bool:
    """Drop ``key`` from the store. Returns True if it was present,
    False otherwise. No fuzzy match — operator (or agent) must use
    the actual stored key, which prevents accidental wide deletes."""
    with _lock:
        facts = _read_facts_raw(instance_dir)
        if key not in facts:
            # Try fuzzy match for the agent's convenience — but only
            # when there's exactly one match, to avoid surprises.
            needle = key.lower().strip()
            candidates = [
                k for k in facts
                if needle in k.lower().replace("_", " ")
                or needle.replace(" ", "_") in k.lower()
            ]
            if len(candidates) == 1:
                key = candidates[0]
            else:
                return False
        del facts[key]
        _write_facts_atomic(facts, instance_dir)
    return True


def list_facts(instance_dir: Path | None = None) -> dict[str, str]:
    """Return the full facts dict (k -> v). Empty {} if nothing
    saved yet."""
    with _lock:
        return _read_facts_raw(instance_dir)


__all__ = [
    "SCHEMA_VERSION",
    "forget",
    "list_facts",
    "recall",
    "remember",
]
