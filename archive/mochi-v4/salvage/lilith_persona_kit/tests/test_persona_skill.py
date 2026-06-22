"""Tests for the ``persona`` skill (Hermes-side ``lilith_persona``).

The skill wraps :class:`lilith.core.persona.PersonaEditor` against the
active-persona file. Tests redirect ``active_persona_path`` at a tmp
file so they never touch the developer's real persona.
"""

from __future__ import annotations

import importlib
import json
import pathlib
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

yaml = pytest.importorskip("yaml")

from jaeger_os.core.permissions import (
    AllowAllProvider,
    PermissionPolicy,
    PermissionTier,
    get_tier,
    use_policy,
)


SKILL_DIR = (
    pathlib.Path(__file__).resolve().parents[5]
    / "src/jaeger_os/instance/lilith/skills/persona"
)


@pytest.fixture
def isolated_persona(tmp_path: pathlib.Path) -> Iterator[Any]:
    """Point the persona skill at a temp ``active.json`` for the test.

    Re-imports the server with ``active_persona_path`` patched, so
    every tool call writes/reads the temp file instead of the user's
    real ``~/.lilith/profiles/active.json``."""
    active = tmp_path / "active.json"
    with patch(
        "jaeger_os.core.persona.active_persona_path", return_value=active
    ):
        import jaeger_os.instance.lilith.skills.persona.server as server_mod

        importlib.reload(server_mod)
        yield server_mod


# --- manifest ---------------------------------------------------------------


def test_manifest_loads() -> None:
    with (SKILL_DIR / "manifest.yaml").open("r", encoding="utf-8") as f:
        m = yaml.safe_load(f)
    assert m["name"] == "persona"
    assert m["category"] == "cognitive"
    assert m["permission_tier"] == 1
    assert m["entry_point"] == (
        "jaeger_os.instance.lilith.skills.persona.server:server"
    )


# --- tier annotations -------------------------------------------------------


def test_read_traits_is_tier_0(isolated_persona: Any) -> None:
    assert get_tier(isolated_persona.read_traits) == PermissionTier.READ_ONLY


def test_writes_are_tier_1(isolated_persona: Any) -> None:
    """Both ``adjust_trait`` and ``bulk_adjust`` mutate the active
    persona file → tier 1 (WRITE_LOCAL), confirmation gated under the
    default policy."""
    s = isolated_persona
    assert get_tier(s.adjust_trait) == PermissionTier.WRITE_LOCAL
    assert get_tier(s.bulk_adjust) == PermissionTier.WRITE_LOCAL


# --- read_traits ------------------------------------------------------------


def test_read_traits_returns_default_when_active_missing(
    isolated_persona: Any,
) -> None:
    """Fresh install / pre-setup: no ``active.json`` yet. ``read_traits``
    returns the default editor's slider values rather than crashing."""
    s = isolated_persona
    out = s.read_traits()
    assert "hexaco" in out and "expression" in out
    assert isinstance(out["hexaco"]["openness"], float)
    assert isinstance(out["expression"]["sarcasm"], float)


# --- adjust_trait -----------------------------------------------------------


def test_adjust_trait_persists_to_active_file(
    isolated_persona: Any, tmp_path: pathlib.Path
) -> None:
    """A single adjustment writes through to ``active.json`` and the
    next ``read_traits`` reflects it."""
    s = isolated_persona
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        result = s.adjust_trait(
            layer="expression", field="sarcasm", value=0.85
        )
    assert result["value"] == 0.85
    assert result["layer"] == "expression"
    assert result["field"] == "sarcasm"
    assert pathlib.Path(result["persisted_to"]).is_file()

    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        traits = s.read_traits()
    assert traits["expression"]["sarcasm"] == 0.85


def test_adjust_trait_clamps_out_of_range(isolated_persona: Any) -> None:
    """Values past ``[0, 1]`` are clamped, not rejected — Lilith
    saying ``adjust_trait(value=3.0)`` should land at 1.0 rather than
    error mid-conversation."""
    s = isolated_persona
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        out = s.adjust_trait(
            layer="expression", field="warmth", value=3.0
        )
    assert out["value"] == 1.0


def test_adjust_trait_rejects_unknown_layer(isolated_persona: Any) -> None:
    s = isolated_persona
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        with pytest.raises(ValueError, match="unknown layer"):
            s.adjust_trait(
                layer="vibe", field="sarcasm", value=0.5
            )


def test_adjust_trait_rejects_unknown_field(isolated_persona: Any) -> None:
    s = isolated_persona
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        with pytest.raises(ValueError, match="unknown field"):
            s.adjust_trait(
                layer="expression", field="snark", value=0.5
            )


def test_adjust_trait_rejects_non_numeric_value(
    isolated_persona: Any,
) -> None:
    s = isolated_persona
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        with pytest.raises(ValueError, match="must be a number"):
            s.adjust_trait(
                layer="expression", field="sarcasm", value="lots"
            )


# --- bulk_adjust ------------------------------------------------------------


def test_bulk_adjust_applies_all_in_order(
    isolated_persona: Any, tmp_path: pathlib.Path
) -> None:
    """Compound user request: ``be warmer and less sarcastic``. One
    file write, both sliders updated."""
    s = isolated_persona
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        out = s.bulk_adjust(
            changes=[
                {"layer": "expression", "field": "warmth", "value": 0.85},
                {"layer": "expression", "field": "sarcasm", "value": 0.10},
            ]
        )
    assert len(out["changes"]) == 2
    assert pathlib.Path(out["persisted_to"]).is_file()

    data = json.loads(
        pathlib.Path(out["persisted_to"]).read_text(encoding="utf-8")
    )
    assert data["expression"]["warmth"] == 0.85
    assert data["expression"]["sarcasm"] == 0.10


def test_bulk_adjust_validates_before_writing(
    isolated_persona: Any,
) -> None:
    """If ANY entry is malformed, NOTHING is written. Prevents the
    half-applied state where the first slider lands but the second
    fails validation."""
    s = isolated_persona
    # Snapshot the pre-write file state.
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        before = s.read_traits()

        with pytest.raises(ValueError, match="unknown field"):
            s.bulk_adjust(
                changes=[
                    {"layer": "expression", "field": "warmth", "value": 0.9},
                    {"layer": "expression", "field": "snarkiness", "value": 0.9},
                ]
            )

        after = s.read_traits()
    # Atomic: warmth was NOT bumped because snarkiness failed validation.
    assert before["expression"]["warmth"] == after["expression"]["warmth"]


def test_bulk_adjust_rejects_empty_list(isolated_persona: Any) -> None:
    s = isolated_persona
    with use_policy(PermissionPolicy(confirmation=AllowAllProvider())):
        with pytest.raises(ValueError, match="non-empty list"):
            s.bulk_adjust(changes=[])
