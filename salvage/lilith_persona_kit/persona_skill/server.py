"""``lilith_persona`` MCP server — conversational persona editing.

Tools:

  read_traits()
      Return the current slider values for every layer. Useful when
      the user asks "what's your personality like right now?" or when
      Lilith needs to know her current state before deciding how to
      adjust.

  adjust_trait(layer, field, value)
      Set a single slider. ``layer`` is one of "hexaco" / "special" /
      "expression" / "domains"; ``field`` is the slider name within
      that layer; ``value`` is clamped to ``[0.0, 1.0]``. Writes
      through to ``~/.lilith/profiles/active.json`` so the change
      survives a restart.

  bulk_adjust(changes)
      Apply multiple adjustments in one call. ``changes`` is a list of
      ``{"layer": ..., "field": ..., "value": ...}`` dicts. Cheaper
      than a series of single calls when the user makes a compound
      request ("be warmer and less sarcastic").

The active-persona file is the canonical store. The live system
prompt rebuilds on the next turn that picks up the new file — Lilith's
launcher reads ``active.json`` at boot, and the bus exposes
``event/persona/changed`` for hot-reload paths (Studio uses this).
This skill writes the file directly; UI consumers can subscribe to
the bus event by watching the file mtime if they want to be told.

# PORTABILITY: Layer 2 (skills/cognitive). Pure file IO + persona
# core; no Lilith-runtime coupling so a Jaeger embodiment can wire
# the same skill against its own persona file.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from jaeger_os.core.permissions import PermissionTier, requires_tier
from jaeger_os.core.persona import (
    PersonaEditor,
    active_persona_path,
)


logger = logging.getLogger(__name__)


server = FastMCP("lilith_persona")


_VALID_LAYERS = {"hexaco", "special", "expression", "domains"}


_LAYER_FIELDS: dict[str, tuple[str, ...]] = {
    "hexaco": (
        "openness", "conscientiousness", "extraversion",
        "agreeableness", "neuroticism", "honesty_humility",
    ),
    "special": (
        "strength", "perception", "endurance", "charisma",
        "intelligence", "agility", "luck",
    ),
    "expression": (
        "sarcasm", "warmth", "verbosity", "formality",
        "directness", "humor", "empathy", "aggression",
    ),
    "domains": (
        "science", "philosophy", "combat", "art",
        "politics", "technology", "nature", "psychology",
    ),
}


def _load_editor() -> PersonaEditor:
    """Load the active persona into a mutable editor.

    Falls back to a default :class:`PersonaEditor` when the active
    file is missing — that way a fresh install can take "be more
    sarcastic" before ``--setup`` has been run, and the resulting
    file becomes the new active persona.
    """
    return PersonaEditor.from_path(active_persona_path())


def _save_editor(editor: PersonaEditor) -> str:
    """Write the editor back to ``~/.lilith/profiles/active.json``.

    Returns the file path as a string so the caller can include it in
    the tool result for trace visibility.
    """
    target = active_persona_path()
    editor.save(target)
    return str(target)


def _layer_to_dict(editor: PersonaEditor, layer: str) -> dict[str, float]:
    target = getattr(editor, layer)
    return {
        field: float(getattr(target, field))
        for field in _LAYER_FIELDS[layer]
    }


def _clamp_value(raw: Any) -> float:
    """Clamp ``raw`` to ``[0.0, 1.0]``. Raises on non-numeric input
    so the LLM gets a clear error rather than silently writing 0.5
    over a real slider."""
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"value must be a number between 0.0 and 1.0; got {raw!r}"
        ) from exc
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


@server.tool(
    name="read_traits",
    description=(
        "Return Lilith's current personality slider values. Use this "
        "when the user asks about her personality, or before deciding "
        "an adjustment so you can frame the change in context (\"you're "
        "currently at sarcasm 0.6; raising to 0.85\")."
    ),
)
@requires_tier(
    PermissionTier.READ_ONLY,
    skill="persona",
    operation="read_traits",
    summary="read the active persona's slider values",
)
def read_traits() -> dict[str, Any]:
    editor = _load_editor()
    return {
        "name": editor.meta.name,
        "description": editor.meta.description,
        "custom_instructions": editor.meta.custom_instructions,
        "hexaco": _layer_to_dict(editor, "hexaco"),
        "special": _layer_to_dict(editor, "special"),
        "expression": _layer_to_dict(editor, "expression"),
        "domains": _layer_to_dict(editor, "domains"),
    }


@server.tool(
    name="adjust_trait",
    description=(
        "Set ONE personality slider. ``layer`` is 'hexaco' / 'special' / "
        "'expression' / 'domains'. ``field`` is the slider name within "
        "that layer (e.g. layer='expression' field='sarcasm'). ``value`` "
        "is 0.0-1.0 (clamped). Persists to ~/.lilith/profiles/active.json. "
        "Use when the user gives a single direction (\"be more sarcastic\", "
        "\"tone down the formality\"). The new shape takes effect on the "
        "next turn / next launch."
    ),
)
@requires_tier(
    PermissionTier.WRITE_LOCAL,
    skill="persona",
    operation="adjust_trait",
    summary="set one personality slider",
)
def adjust_trait(layer: str, field: str, value: float) -> dict[str, Any]:
    layer = (layer or "").strip().lower()
    field = (field or "").strip().lower()
    if layer not in _VALID_LAYERS:
        raise ValueError(
            f"unknown layer {layer!r}; expected one of "
            f"{sorted(_VALID_LAYERS)}"
        )
    if field not in _LAYER_FIELDS[layer]:
        raise ValueError(
            f"unknown field {field!r} for layer {layer!r}; expected one "
            f"of {list(_LAYER_FIELDS[layer])}"
        )
    clamped = _clamp_value(value)

    editor = _load_editor()
    target_layer = getattr(editor, layer)
    previous = float(getattr(target_layer, field))
    setattr(target_layer, field, clamped)
    saved_path = _save_editor(editor)

    return {
        "layer": layer,
        "field": field,
        "previous": previous,
        "value": clamped,
        "persisted_to": saved_path,
    }


@server.tool(
    name="bulk_adjust",
    description=(
        "Apply multiple slider adjustments in one call. ``changes`` is "
        "a list of {layer, field, value} dicts. Cheaper than calling "
        "adjust_trait once per slider when the user gives a compound "
        "request (\"be warmer and less sarcastic\"). All changes are "
        "validated first; if any item is malformed, NOTHING is written "
        "and the call raises."
    ),
)
@requires_tier(
    PermissionTier.WRITE_LOCAL,
    skill="persona",
    operation="bulk_adjust",
    summary="apply multiple personality slider adjustments",
)
def bulk_adjust(changes: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(changes, list) or not changes:
        raise ValueError(
            "changes must be a non-empty list of "
            "{layer, field, value} dicts"
        )
    # Validate every entry up-front so a partial-write never lands.
    parsed: list[tuple[str, str, float]] = []
    for idx, entry in enumerate(changes):
        if not isinstance(entry, dict):
            raise ValueError(
                f"changes[{idx}] must be a dict, got {type(entry).__name__}"
            )
        layer = (entry.get("layer") or "").strip().lower()
        field = (entry.get("field") or "").strip().lower()
        value = entry.get("value")
        if layer not in _VALID_LAYERS:
            raise ValueError(
                f"changes[{idx}]: unknown layer {layer!r}"
            )
        if field not in _LAYER_FIELDS[layer]:
            raise ValueError(
                f"changes[{idx}]: unknown field {field!r} for layer "
                f"{layer!r}"
            )
        parsed.append((layer, field, _clamp_value(value)))

    editor = _load_editor()
    applied: list[dict[str, Any]] = []
    for layer, field, clamped in parsed:
        target_layer = getattr(editor, layer)
        previous = float(getattr(target_layer, field))
        setattr(target_layer, field, clamped)
        applied.append(
            {
                "layer": layer,
                "field": field,
                "previous": previous,
                "value": clamped,
            }
        )
    saved_path = _save_editor(editor)
    return {"changes": applied, "persisted_to": saved_path}


# ----- Process entry point -------------------------------------------------


if __name__ == "__main__":  # pragma: no cover - process entry point
    server.run()
