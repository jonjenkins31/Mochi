"""Reading a character pack.

A character is a self-contained folder with a ``character.yaml`` that
declares everything needed to play it: which adapter renders it, the
atlas geometry, and — the part that matters — its OWN vocabulary of
expressions.

That vocabulary is the persona boundary. The animation engine knows
about sprite cells; it has never heard of "happy". Mochi reads the
mapping from the pack, so a different character with different words
plays through the same engine with no code change. Put the word list
in code and you have written one character into the app forever.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

import yaml

#: Character packs ship with the animation module. Mochi has none of
#: its own — a player that bundled a character would be that character.
_PACK_ROOTS: tuple[str, ...] = (
    "jaeger_animation/assets/characters",
)


class CharacterError(RuntimeError):
    """A pack that cannot be played, saying which rule it broke."""


@dataclass(frozen=True)
class Character:
    """A loaded pack, ready to turn expressions into play commands."""

    name: str
    directory: pathlib.Path
    adapter: str
    asset: pathlib.Path
    grid: tuple[int, int]                 # cols, rows
    expressions: dict[str, int]           # name -> column
    mouth_states: dict[str, int]          # name -> row
    default_expression: str
    default_mouth: str
    scaling: str

    def cell(self, expression: str, mouth: str | None = None) -> int:
        """Atlas cell index for one expression + mouth state.

        Row-major, because that is what the pack declares and what the
        sprite adapter expects: ``row * cols + column``. The two axes
        are the whole reason this is a grid rather than a strip —
        holding an expression and alternating the mouth row IS the
        talking animation.
        """
        if expression not in self.expressions:
            raise CharacterError(
                f"{self.name!r} has no expression {expression!r}; "
                f"it declares {sorted(self.expressions)}")
        mouth = mouth or self.default_mouth
        if mouth not in self.mouth_states:
            raise CharacterError(
                f"{self.name!r} has no mouth state {mouth!r}; "
                f"it declares {sorted(self.mouth_states)}")
        cols, _ = self.grid
        return self.mouth_states[mouth] * cols + self.expressions[expression]

    def play_params(self, expression: str, mouth: str | None = None) -> dict:
        """The ``params`` block for a DisplayCommand."""
        return {
            "grid": tuple(self.grid),
            "cell": self.cell(expression, mouth),
            "scaling": self.scaling,
        }

    @property
    def expression_names(self) -> list[str]:
        return list(self.expressions)


def _pack_dir(name: str) -> pathlib.Path:
    """Find a character pack among the installed module roots."""
    import importlib.util

    tried: list[str] = []
    for root in _PACK_ROOTS:
        pkg = root.split("/")[0]
        spec = importlib.util.find_spec(pkg)
        if spec is None or not spec.submodule_search_locations:
            tried.append(f"{pkg} (not installed)")
            continue
        base = pathlib.Path(list(spec.submodule_search_locations)[0]).parent
        candidate = base / root / name
        tried.append(str(candidate))
        if (candidate / "character.yaml").is_file():
            return candidate
    raise CharacterError(
        f"no character pack {name!r}. Looked in: {'; '.join(tried)}")


def load(name: str) -> Character:
    """Load a character pack by name."""
    directory = _pack_dir(name)
    doc: dict[str, Any] = yaml.safe_load(
        (directory / "character.yaml").read_text(encoding="utf-8")) or {}

    schema = doc.get("schema", "")
    if not schema.startswith("character/"):
        raise CharacterError(
            f"{directory}: schema {schema!r} is not a character pack")

    render = doc.get("render") or {}
    for field in ("adapter", "asset", "grid"):
        if field not in render:
            raise CharacterError(f"{directory}: render.{field} is required")

    asset = directory / render["asset"]
    if not asset.is_file():
        raise CharacterError(
            f"{directory}: render.asset {render['asset']!r} does not exist")

    expressions = {
        name_: int(body["column"])
        for name_, body in (doc.get("expressions") or {}).items()
    }
    if not expressions:
        raise CharacterError(f"{directory}: declares no expressions")

    mouth_states = {k: int(v) for k, v in (doc.get("mouth_states") or {}).items()}
    if not mouth_states:
        # A character with no mouth axis is legal — a single-row strip
        # of stills. Give it one row so `cell()` stays uniform.
        mouth_states = {"closed": 0}

    default_expression = doc.get("default_expression") or next(iter(expressions))
    default_mouth = doc.get("default_mouth") or next(iter(mouth_states))
    if default_expression not in expressions:
        raise CharacterError(
            f"{directory}: default_expression {default_expression!r} "
            f"is not among {sorted(expressions)}")

    cols, rows = render["grid"]
    return Character(
        name=doc.get("character") or name,
        directory=directory,
        adapter=render["adapter"],
        asset=asset,
        grid=(int(cols), int(rows)),
        expressions=expressions,
        mouth_states=mouth_states,
        default_expression=default_expression,
        default_mouth=default_mouth,
        scaling=render.get("scaling", "nearest"),
    )


__all__ = ["Character", "CharacterError", "load"]
