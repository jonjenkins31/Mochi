"""Character — a library preset on top of :class:`Personality`.

``personality/`` IS the character logic: :mod:`schema` holds the trait model
(HEXACO/SPECIAL/Expression/Domains + custom_instructions) and :mod:`compose`
renders it into the system prompt. A *character* is just that ``Personality``
plus the library extras — identity (role/voice), backstory, and assets
(card/avatar) — stored as a folder ``personality/characters/<id>/``.

Only ``custom_instructions`` feeds the model today; the trait ratings are
stored + shown on the profile and drive behavior in a later update.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import msgspec
import yaml

from mochi.personality.schema import (
    HEXACO, SPECIAL, Domains, Expression, Personality,
)


def _u(x: Any) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.5


def _layer(cls: type, data: dict[str, Any]) -> Any:
    known = set(cls.__struct_fields__)
    return cls(**{k: _u(v) for k, v in (data or {}).items() if k in known})


@dataclass
class Character:
    """A character = a :class:`Personality` + identity + assets."""

    id: str
    personality: Personality
    role: str = ""
    voice_tone: str = ""
    voice_id: str = "af_heart"
    backstory: str = ""
    soul: str = ""
    quotes: tuple[str, ...] = ()
    mannerisms: tuple[str, ...] = ()
    ideals: tuple[str, ...] = ()
    behaviors: tuple[str, ...] = ()
    card: str = ""
    avatar_dir: str = "avatar"
    root: Path | None = None

    @property
    def name(self) -> str:
        return self.personality.name or self.id

    @property
    def description(self) -> str:
        return self.personality.description

    def identity_block(self) -> str:
        """Concise 'who you are' — drives the identity prompt fragment."""
        return (f"You are {self.name}. {self.role}".strip()
                if self.role else f"You are {self.name}.")

    def _bullets(self, label: str, items: tuple[str, ...], quote: bool = False) -> str:
        if not items:
            return ""
        body = "\n".join((f'- "{x}"' if quote else f"- {x}") for x in items)
        return f"{label}:\n{body}"

    def soul_block(self) -> str:
        """The full persona the model sees — definition + narrative + lore.
        Drives the soul fragment. (Trait ratings still drive behavior later.)"""
        p = self.personality
        parts = [
            p.custom_instructions.strip() if p.custom_instructions else "",
            self.soul.strip(),
            self._bullets("Ideals", self.ideals),
            self._bullets("Mannerisms", self.mannerisms),
            self._bullets("Behaviors", self.behaviors),
            self._bullets("Speech patterns", tuple(p.speech_patterns)),
            self._bullets("Signature lines", self.quotes, quote=True),
            ("Backstory: " + self.backstory.strip()[:600]) if self.backstory else "",
        ]
        return "\n\n".join(x for x in parts if x)

    def prompt(self) -> str:
        """Alias for the full persona text (used by the Studio profile)."""
        return self.soul_block()

    def card_path(self) -> Path | None:
        if self.root and self.card:
            p = self.root / self.card
            return p if p.exists() else None
        return None


def load_character(folder: Path) -> Character:
    """Load ``<folder>/character.yaml`` → a :class:`Character`."""
    folder = Path(folder)
    data = yaml.safe_load((folder / "character.yaml").read_text(encoding="utf-8")) or {}
    ident = data.get("identity", {}) or {}
    pr = data.get("prompt", {}) or {}
    tr = data.get("traits", {}) or {}
    assets = data.get("assets", {}) or {}
    personality = Personality(
        name=data.get("name", folder.name),
        description=data.get("description", ""),
        custom_instructions=pr.get("custom_instructions", ""),
        speech_patterns=tuple(pr.get("speech_patterns", []) or ()),
        hexaco=_layer(HEXACO, tr.get("hexaco", {})),
        special=_layer(SPECIAL, tr.get("special", {})),
        expression=_layer(Expression, tr.get("expression", {})),
        domains=_layer(Domains, tr.get("domains", {})),
    )
    lore = data.get("lore", {}) or {}
    return Character(
        id=data.get("id", folder.name),
        personality=personality,
        role=ident.get("role", ""),
        voice_tone=ident.get("voice_tone", ""),
        voice_id=ident.get("voice_id", "af_heart"),
        backstory=pr.get("backstory", ""),
        soul=pr.get("soul", ""),
        quotes=tuple(lore.get("quotes", []) or ()),
        mannerisms=tuple(lore.get("mannerisms", []) or ()),
        ideals=tuple(lore.get("ideals", []) or ()),
        behaviors=tuple(lore.get("behaviors", []) or ()),
        card=assets.get("card", ""),
        avatar_dir=assets.get("avatar", "avatar"),
        root=folder,
    )


def characters_root() -> Path:
    """The bundled character library — ``personality/characters/``."""
    return Path(__file__).resolve().parent / "characters"


def list_characters(root: Path | None = None) -> list[Character]:
    """Every character folder under ``root`` (default: the bundled library),
    sorted by name. Skips folders without a character.yaml."""
    root = Path(root) if root else characters_root()
    out: list[Character] = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "character.yaml").exists():
            try:
                out.append(load_character(d))
            except Exception:  # noqa: BLE001 — one bad sheet never breaks the library
                continue
    return sorted(out, key=lambda c: c.name.lower())


# msgspec struct -> dict, for the profile UI to iterate trait sliders.
def layer_items(struct: Any) -> list[tuple[str, float]]:
    return list(msgspec.structs.asdict(struct).items())


# ── active character (which character an instance plays) ────────────
_ACTIVE_FILE = "active_character"


def active_character_id(instance_root: Path) -> str:
    f = Path(instance_root) / _ACTIVE_FILE
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


def set_active_character(instance_root: Path, cid: str) -> None:
    """Set the character this instance plays (writes <instance>/active_character)."""
    root = Path(instance_root); root.mkdir(parents=True, exist_ok=True)
    (root / _ACTIVE_FILE).write_text(cid.strip(), encoding="utf-8")


def active_character(instance_root: Path) -> "Character | None":
    """The character this instance plays, or None. Its prompt replaces the
    instance personality block (see agent/prompts/assemble.py)."""
    cid = active_character_id(instance_root)
    folder = characters_root() / cid
    if cid and (folder / "character.yaml").exists():
        try:
            return load_character(folder)
        except Exception:  # noqa: BLE001
            return None
    return None
