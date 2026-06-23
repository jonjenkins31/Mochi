"""Character model — the unified character sheet.

A *character* is a folder ``characters/<id>/`` with a ``character.yaml``
sheet + assets. The sheet stores everything: identity (name/role/voice),
the prompt the LLM sees today (``custom_instructions``), and the full trait
layers (HEXACO / SPECIAL / Expression / Domains) — stored now so the
pipeline is ready, even though only the prompt drives the model today and
trait ratings/levels land in a later update.

Trait layers are ported verbatim from the archive lilith_persona_kit so the
profile page can render them and future work can wire them into behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


def _clamp01(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return 0.0 if f < 0.0 else 1.0 if f > 1.0 else f


# ── trait layers (0..1 sliders) — stored, not yet driving the LLM ───

@dataclass(frozen=True)
class HexacoLayer:
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5
    honesty_humility: float = 0.8


@dataclass(frozen=True)
class SpecialLayer:
    strength: float = 0.5
    perception: float = 0.5
    endurance: float = 0.5
    charisma: float = 0.5
    intelligence: float = 0.7
    agility: float = 0.5
    luck: float = 0.5


@dataclass(frozen=True)
class ExpressionLayer:
    sarcasm: float = 0.2
    warmth: float = 0.3
    verbosity: float = 0.4
    formality: float = 0.6
    directness: float = 0.8
    humor: float = 0.3
    empathy: float = 0.4
    aggression: float = 0.2


@dataclass(frozen=True)
class DomainsLayer:
    science: float = 0.6
    philosophy: float = 0.5
    technology: float = 0.8
    art: float = 0.4
    politics: float = 0.3
    nature: float = 0.4
    psychology: float = 0.5
    combat: float = 0.3


def _layer(cls: type, data: dict[str, Any]) -> Any:
    """Build a frozen trait layer from a dict, clamping to [0,1] and
    ignoring unknown keys (forward/backward compatible)."""
    known = {f.name for f in fields(cls)}
    vals = {k: _clamp01(v) for k, v in (data or {}).items() if k in known}
    return cls(**vals)


@dataclass(frozen=True)
class Traits:
    hexaco: HexacoLayer = field(default_factory=HexacoLayer)
    special: SpecialLayer = field(default_factory=SpecialLayer)
    expression: ExpressionLayer = field(default_factory=ExpressionLayer)
    domains: DomainsLayer = field(default_factory=DomainsLayer)

    def to_dict(self) -> dict[str, Any]:
        return {k: asdict(getattr(self, k))
                for k in ("hexaco", "special", "expression", "domains")}


# ── character ───────────────────────────────────────────────────────

@dataclass
class Character:
    id: str
    name: str
    description: str = ""
    # identity (persona/v1 carryover)
    role: str = ""
    voice_tone: str = ""
    voice_id: str = "af_heart"
    # what the LLM sees TODAY
    custom_instructions: str = ""
    backstory: str = ""
    speech_patterns: tuple[str, ...] = ()
    # stored structure for future behavior + the profile page
    traits: Traits = field(default_factory=Traits)
    # asset paths, relative to the character folder
    card: str = ""
    avatar_dir: str = "avatar"
    root: Path | None = None

    def prompt(self) -> str:
        """The character text the model sees today — just the defining
        instructions (+ speech patterns / backstory when present). Trait
        ratings are NOT injected yet; that's a later update."""
        parts = [self.custom_instructions.strip()] if self.custom_instructions else []
        if self.speech_patterns:
            parts.append("Speech patterns:\n" + "\n".join(f"- {s}" for s in self.speech_patterns))
        if self.backstory:
            parts.append("Backstory: " + self.backstory.strip()[:400])
        return "\n\n".join(p for p in parts if p)

    def card_path(self) -> Path | None:
        if self.root and self.card:
            p = self.root / self.card
            return p if p.exists() else None
        return None


def character_from_dict(data: dict[str, Any], *, cid: str, root: Path | None = None) -> Character:
    ident = data.get("identity", {}) or {}
    prompt = data.get("prompt", {}) or {}
    t = data.get("traits", {}) or {}
    assets = data.get("assets", {}) or {}
    return Character(
        id=data.get("id", cid),
        name=data.get("name", cid),
        description=data.get("description", ""),
        role=ident.get("role", ""),
        voice_tone=ident.get("voice_tone", ""),
        voice_id=ident.get("voice_id", "af_heart"),
        custom_instructions=prompt.get("custom_instructions", ""),
        backstory=prompt.get("backstory", ""),
        speech_patterns=tuple(prompt.get("speech_patterns", []) or ()),
        traits=Traits(
            hexaco=_layer(HexacoLayer, t.get("hexaco", {})),
            special=_layer(SpecialLayer, t.get("special", {})),
            expression=_layer(ExpressionLayer, t.get("expression", {})),
            domains=_layer(DomainsLayer, t.get("domains", {})),
        ),
        card=assets.get("card", ""),
        avatar_dir=assets.get("avatar", "avatar"),
        root=root,
    )


def load_character(folder: Path) -> Character:
    """Load ``<folder>/character.yaml`` into a :class:`Character`."""
    folder = Path(folder)
    data = yaml.safe_load((folder / "character.yaml").read_text(encoding="utf-8")) or {}
    return character_from_dict(data, cid=folder.name, root=folder)


def characters_root() -> Path:
    """The bundled character library: ``<repo>/mochi/characters``."""
    return Path(__file__).resolve().parents[1] / "characters"


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
