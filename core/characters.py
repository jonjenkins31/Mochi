"""Finding character packs — project copies first.

Reading and validating a pack is NOT this app's job. The format is the
contract between Anima Studio and JaegerAnimation, and the animation
module owns the reader: `jaeger_animation.characters` parses it,
validates it, and turns an expression into adapter params.

This file is the twenty lines that are genuinely Mochi's: WHERE to
look. Packs in this project's `assets/characters/` win over the demo
bundled in the module, the same way `modules/` wins over an installed
module.

There was a 209-line reimplementation here until 2026-07-27. It parsed
the same YAML, built the same cell indices, and raised different error
messages — two copies of one truth, and the one in the module was
better (it refuses a `kind` it cannot render instead of silently
showing nothing).
"""

from __future__ import annotations

import pathlib

from jaeger_animation.characters import (  # the module owns the format
    BUILTIN_DIR, Character, CharacterError, discover_characters,
)

#: Where a pack exported from Anima Studio lands. Searched FIRST.
PROJECT_CHARACTERS = pathlib.Path("assets/characters")


def project_root() -> pathlib.Path:
    """The project directory — where assets/ and jaeger.toml live."""
    return pathlib.Path(__file__).resolve().parent.parent


def _roots() -> tuple[pathlib.Path, ...]:
    """Roots in PRECEDENCE-LAST order.

    `discover_characters` builds a dict keyed by name, so a later root
    OVERWRITES an earlier one. Built-ins therefore come first and the
    project's own packs last — the reverse of how it reads, which is
    exactly why it is spelled out here. Written the intuitive way round
    the overlay silently inverts and you edit a pack in
    assets/characters/ while the venv copy is what plays.
    """
    return (BUILTIN_DIR, project_root() / PROJECT_CHARACTERS)


def available() -> list[str]:
    """Every playable pack. Installing one is copying a folder."""
    return sorted(discover_characters(_roots()))


def load(name: str) -> Character:
    """Load a pack by name, project copy winning."""
    found = discover_characters(_roots())
    if name not in found:
        raise CharacterError(
            f"no character pack {name!r}. Looked in: "
            f"{', '.join(str(r) for r in _roots())}. "
            f"Found: {sorted(found) or 'none'}"
        )
    return found[name]


__all__ = ["Character", "CharacterError", "available", "load",
           "project_root", "PROJECT_CHARACTERS"]
