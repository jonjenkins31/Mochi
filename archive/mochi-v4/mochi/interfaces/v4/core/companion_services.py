"""Toolkit-neutral companion services.

The PySide companion should render state and collect intent; durable
rules live here so a future Swift/TUI/web surface can reuse them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PLAYER_SETTINGS: dict[str, Any] = {
    "canvas_w": 512,
    "canvas_h": 512,
    "topmost": True,
    "opacity": 1.0,
    "default_framing": "stretch",
}

NO_HANDLER_TYPES: dict[str, str] = {
    "animations": "eye-blink JSONs (left/right eye sprite refs)",
    "procedural": "procedural JSON configs (color_wheel)",
}


@dataclass(frozen=True)
class AnimationCommand:
    """Resolved animation intent from a catalog entry or named asset."""

    command: str
    recent_name: str


@dataclass(frozen=True)
class UnsupportedAnimation:
    """Catalog entry that is visible but cannot currently render."""

    entry_type: str
    reason: str
    name: str

    @property
    def message(self) -> str:
        return (
            f"type={self.entry_type!r} ({self.reason}) has no runtime "
            f"handler yet - {self.name!r} won't activate. Try a gif, "
            "math, mscript, or bitmap entry."
        )


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"entries": []}
    return data if isinstance(data, dict) else {"entries": []}


def normalize_player_settings(data: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_PLAYER_SETTINGS)
    if not isinstance(data, dict):
        return out
    for key, default in DEFAULT_PLAYER_SETTINGS.items():
        value = data.get(key, default)
        if isinstance(default, bool):
            out[key] = bool(value)
        elif isinstance(default, int):
            try:
                out[key] = int(value)
            except (TypeError, ValueError):
                out[key] = default
        elif isinstance(default, float):
            try:
                out[key] = float(value)
            except (TypeError, ValueError):
                out[key] = default
        else:
            out[key] = value
    return out


class PlayerSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return normalize_player_settings(None)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = None
        return normalize_player_settings(data)

    def save(self, settings: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        merged = normalize_player_settings({**self.load(), **(settings or {})})
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


class RecentStore:
    def __init__(self, path: Path, *, max_items: int = 10) -> None:
        self.path = path
        self.max_items = max(1, int(max_items))

    def load(self) -> list[str]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(data, list):
            return []
        return [str(x) for x in data if isinstance(x, str)][: self.max_items]

    def save(self, items: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        cleaned = [str(x) for x in items if x][: self.max_items]
        self.path.write_text(
            json.dumps(cleaned, indent=2) + "\n",
            encoding="utf-8",
        )

    def push(self, name: str) -> list[str]:
        if not name:
            return self.load()
        items = self.load()
        if name in items:
            items.remove(name)
        items.insert(0, name)
        items = items[: self.max_items]
        self.save(items)
        return items


def catalog_entry_identity(entry: dict[str, Any]) -> str:
    path = str(entry.get("path", "") or "")
    return Path(path).stem if path else str(entry.get("name", "") or "")


def is_curated(entry: dict[str, Any]) -> bool:
    """Return whether a catalog entry has operator-authored metadata."""
    return bool(entry.get("author"))


def filter_catalog_entries(
    entries: list[dict[str, Any]],
    *,
    mood: str = "all",
    type_: str = "all",
    curation: str = "all",
    search_text: str = "",
) -> list[dict[str, Any]]:
    search = (search_text or "").lower().strip()
    results: list[dict[str, Any]] = []
    for entry in entries:
        if mood != "all" and entry.get("mood") != mood:
            continue
        if type_ != "all" and entry.get("type") != type_:
            continue
        curated = is_curated(entry)
        if curation == "curated" and not curated:
            continue
        if curation == "uncurated" and curated:
            continue
        if search:
            haystack = " ".join([
                str(entry.get("name", "")),
                str(entry.get("type", "")),
                " ".join(str(tag) for tag in entry.get("tags", [])),
                str(entry.get("hint", "")),
            ]).lower()
            if search not in haystack:
                continue
        results.append(entry)
    return results


def command_for_catalog_entry(
    entry: dict[str, Any],
) -> AnimationCommand | UnsupportedAnimation | None:
    name = catalog_entry_identity(entry)
    if not name:
        return None
    entry_type = str(entry.get("type", "") or "")
    reason = NO_HANDLER_TYPES.get(entry_type)
    if reason:
        return UnsupportedAnimation(entry_type=entry_type, reason=reason, name=name)
    path = str(entry.get("path", "") or "")
    if entry_type == "mscripts":
        return AnimationCommand(command=f"play {path}", recent_name=name)
    return AnimationCommand(
        command=mode_on_command(name),
        recent_name=name,
    )


def command_for_slot_value(slot_value: Any) -> AnimationCommand | None:
    if isinstance(slot_value, list):
        slot_value = slot_value[0] if slot_value else None
    if isinstance(slot_value, dict):
        slot_value = slot_value.get("file") or slot_value.get("name")
    if not slot_value:
        return None
    name = Path(str(slot_value)).stem
    if not name:
        return None
    return AnimationCommand(command=mode_on_command(name), recent_name=name)


def mode_on_command(name: str) -> str:
    return f"node animation mode on {name}"


def mode_off_command() -> str:
    return "node animation mode off"


def size_command(width: int, height: int) -> str:
    return f"node animation size {int(width)}x{int(height)}"


def framing_command(mode: str) -> str:
    return f"node animation framing {(mode or '').lower()}"


def color_command(rgb: tuple[int, int, int], target: str | None = None) -> str:
    r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    if target:
        return f"node animation color {target} {r} {g} {b}"
    return f"node animation color {r} {g} {b}"


__all__ = [
    "AnimationCommand",
    "DEFAULT_PLAYER_SETTINGS",
    "NO_HANDLER_TYPES",
    "PlayerSettingsStore",
    "RecentStore",
    "UnsupportedAnimation",
    "catalog_entry_identity",
    "color_command",
    "command_for_catalog_entry",
    "command_for_slot_value",
    "framing_command",
    "filter_catalog_entries",
    "is_curated",
    "load_catalog",
    "mode_off_command",
    "mode_on_command",
    "normalize_player_settings",
    "size_command",
]
