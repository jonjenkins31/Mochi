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
    card: str = ""
    avatar_dir: str = "avatar"
    root: Path | None = None

    @property
    def name(self) -> str:
        return self.personality.name or self.id

    @property
    def description(self) -> str:
        return self.personality.description

    def prompt(self) -> str:
        """What the model sees TODAY — just the defining instructions
        (+ speech patterns / backstory). Trait-driven prose (compose_block)
        is a later update, deliberately not injected yet."""
        p = self.personality
        parts = [p.custom_instructions.strip()] if p.custom_instructions else []
        if p.speech_patterns:
            parts.append("Speech patterns:\n" + "\n".join(f"- {s}" for s in p.speech_patterns))
        if self.backstory:
            parts.append("Backstory: " + self.backstory.strip()[:400])
        return "\n\n".join(x for x in parts if x)

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
    return Character(
        id=data.get("id", folder.name),
        personality=personality,
        role=ident.get("role", ""),
        voice_tone=ident.get("voice_tone", ""),
        voice_id=ident.get("voice_id", "af_heart"),
        backstory=pr.get("backstory", ""),
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
