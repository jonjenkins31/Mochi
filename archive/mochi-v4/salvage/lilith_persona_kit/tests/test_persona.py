"""Tests for ``lilith.core.persona``."""

from __future__ import annotations

import json
import pathlib

import pytest

from jaeger_os.core.persona import (
    LILITH_DEFAULT_PERSONA,
    DomainsLayer,
    ExpressionLayer,
    HexacoLayer,
    Persona,
    SpecialLayer,
    load_persona,
)


# --- clamping --------------------------------------------------------------


def test_layers_clamp_out_of_range() -> None:
    h = HexacoLayer(openness=2.0, conscientiousness=-1.0)
    assert h.openness == 1.0
    assert h.conscientiousness == 0.0


def test_layers_clamp_non_numeric_to_default_or_zero() -> None:
    h = HexacoLayer(openness="not-a-number")  # type: ignore[arg-type]
    # Non-numeric input falls back to 0.5 (the field default semantics).
    assert h.openness == 0.5


def test_layers_are_frozen() -> None:
    h = HexacoLayer()
    with pytest.raises((AttributeError, Exception)):
        h.openness = 0.9  # type: ignore[misc]


# --- default persona shape -------------------------------------------------


def test_default_persona_label() -> None:
    assert LILITH_DEFAULT_PERSONA.label == "lilith-default"


def test_list_bundled_personas_returns_library() -> None:
    """The 11 V3 personas we copied into the V4 tree are findable.

    A regression on this test means the bundled library got moved or
    deleted — fix the path or restore the files.
    """
    from jaeger_os.core.persona import list_bundled_personas

    names = list_bundled_personas()
    # Must include the headliners we copied in 2026-05-07.
    for expected in ("glados", "bender", "hal_9000", "tars", "lilith"):
        assert expected in names, f"missing bundled persona: {expected}"


def test_resolve_persona_finds_bundled_by_name() -> None:
    """``resolve_persona('glados')`` returns the bundled JSON path."""
    from jaeger_os.core.persona import resolve_persona

    path = resolve_persona("glados")
    assert path.is_file()
    assert path.name == "glados.json"


def test_resolve_persona_accepts_explicit_path(tmp_path) -> None:
    """A path argument bypasses the library lookup."""
    import json

    from jaeger_os.core.persona import resolve_persona

    p = tmp_path / "custom.json"
    p.write_text(json.dumps({"label": "custom"}), encoding="utf-8")
    assert resolve_persona(str(p)) == p
    assert resolve_persona(p) == p


def test_persona_editor_default_is_buildable() -> None:
    """Studio constructs an empty editor on first launch — must not crash."""
    from jaeger_os.core.persona import PersonaEditor

    editor = PersonaEditor()
    assert editor.meta.name == "Lilith"
    assert editor.hexaco.openness == 0.5


def test_persona_editor_round_trips_through_persona() -> None:
    """``PersonaEditor.from_persona(p).to_persona()`` is the identity for
    every field that V4's frozen Persona carries."""
    from jaeger_os.core.persona import LILITH_DEFAULT_PERSONA, PersonaEditor

    editor = PersonaEditor.from_persona(LILITH_DEFAULT_PERSONA)
    assert editor.meta.name == LILITH_DEFAULT_PERSONA.label
    assert editor.hexaco.openness == LILITH_DEFAULT_PERSONA.hexaco.openness
    assert (
        editor.expression.warmth == LILITH_DEFAULT_PERSONA.expression.warmth
    )

    rebuilt = editor.to_persona()
    assert rebuilt == LILITH_DEFAULT_PERSONA


def test_persona_editor_loads_v3_active_json_shape(tmp_path) -> None:
    """V3 personas (with ``meta.*`` nesting + organizational extras)
    load and round-trip without losing the V3-only fields."""
    import json

    from jaeger_os.core.persona import PersonaEditor

    v3_shape = {
        "meta": {
            "name": "GLaDOS",
            "category": "originals",
            "source": "Portal",
            "custom_instructions": "You are GLaDOS.",
            "speech_patterns": ["Use dry wit"],
            "backstory": "Aperture Science",
            "tags": ["ai"],
            "created": "2026-05-01",
        },
        "hexaco": {"openness": 0.6},
        "expression": {"sarcasm": 1.0, "humor": 0.9},
    }
    path = tmp_path / "glados.json"
    path.write_text(json.dumps(v3_shape), encoding="utf-8")

    editor = PersonaEditor.from_path(path)

    # V4 fields populated.
    assert editor.meta.name == "GLaDOS"
    assert editor.meta.custom_instructions == "You are GLaDOS."
    assert editor.meta.speech_patterns == ["Use dry wit"]
    assert editor.meta.backstory == "Aperture Science"
    assert editor.expression.sarcasm == 1.0
    # V3-only organizational fields preserved.
    assert editor.meta.category == "originals"
    assert editor.meta.source == "Portal"
    assert editor.meta.tags == ["ai"]
    assert editor.meta.created == "2026-05-01"


def test_persona_editor_save_round_trip(tmp_path) -> None:
    """``editor.save(path)`` writes JSON that ``from_path`` reads back to
    the same editor state — including V3 organizational extras."""
    from jaeger_os.core.persona import PersonaEditor, PersonaEditorMeta

    editor = PersonaEditor(
        meta=PersonaEditorMeta(
            name="TestPersona",
            description="round-trip target",
            custom_instructions="say hello",
            speech_patterns=["one", "two"],
            backstory="lab origin",
            category="originals",
            source="testbench",
            tags=["test"],
            created="2026-05-07",
        )
    )
    editor.expression.humor = 0.9
    editor.hexaco.openness = 0.85

    path = tmp_path / "rt.json"
    editor.save(path)

    reloaded = PersonaEditor.from_path(path)
    assert reloaded.meta.name == "TestPersona"
    assert reloaded.meta.custom_instructions == "say hello"
    assert reloaded.meta.speech_patterns == ["one", "two"]
    assert reloaded.meta.tags == ["test"]
    assert reloaded.meta.created == "2026-05-07"
    assert reloaded.expression.humor == 0.9
    assert reloaded.hexaco.openness == 0.85


def test_save_persona_accepts_either_persona_or_editor(tmp_path) -> None:
    """V3-style ``save_profile`` mirror — works with both shapes."""
    from jaeger_os.core.persona import (
        LILITH_DEFAULT_PERSONA,
        Persona,
        PersonaEditor,
        save_persona,
    )

    p = tmp_path / "from_persona.json"
    save_persona(LILITH_DEFAULT_PERSONA, p)
    assert PersonaEditor.from_path(p).to_persona() == LILITH_DEFAULT_PERSONA

    e = PersonaEditor.from_persona(LILITH_DEFAULT_PERSONA)
    e.meta.name = "Renamed"
    p2 = tmp_path / "from_editor.json"
    save_persona(e, p2)
    rebuilt: Persona = PersonaEditor.from_path(p2).to_persona()
    assert rebuilt.label == "Renamed"


def test_persona_editor_from_missing_path_returns_default(tmp_path) -> None:
    """A non-existent file must not raise — Studio can still open a fresh
    editor when a saved profile path is no longer there."""
    from jaeger_os.core.persona import PersonaEditor

    editor = PersonaEditor.from_path(tmp_path / "missing.json")
    assert editor.meta.name == "Lilith"


def test_resolve_persona_raises_on_missing() -> None:
    """A bare name with no matching JSON anywhere produces a useful error."""
    import pytest as _pytest

    from jaeger_os.core.persona import resolve_persona

    with _pytest.raises(FileNotFoundError) as excinfo:
        resolve_persona("definitely-not-a-real-persona-xyz")
    assert "definitely-not-a-real-persona-xyz" in str(excinfo.value)


def test_default_persona_matches_identity_voice() -> None:
    """Default persona's expression layer matches Lilith's voice.

    Master prompt §9 originally read 'competent, slightly formal, dry;
    no cute, no warmth-by-default'. Live Mac use surfaced that the
    austere reading made Gemma 4 refuse casual conversation entirely
    (asked for a joke, got 'I don't tell jokes; what task can I do?').
    The revised intent (2026-05-07): she stays formal and direct, but
    has enough warmth + humor to chat and banter when the moment calls
    for it. Sarcasm stays low; aggression stays low; directness stays
    high.
    """
    e = LILITH_DEFAULT_PERSONA.expression
    assert e.directness >= 0.7
    assert e.sarcasm <= 0.3
    assert e.aggression <= 0.3
    assert e.formality >= 0.45  # slightly less than before but still formal-leaning
    # Warmth + humor above the persona overlay's threshold (0.7) so the
    # rendered prompt actually instructs her to weave humor naturally
    # rather than staying mute by default.
    assert e.humor >= 0.6
    assert e.warmth >= 0.5


# --- Serialization ---------------------------------------------------------


def test_persona_round_trips_through_dict() -> None:
    data = LILITH_DEFAULT_PERSONA.to_dict()
    rebuilt = Persona.from_dict(data)
    assert rebuilt == LILITH_DEFAULT_PERSONA


def test_persona_from_dict_tolerates_missing_layers() -> None:
    """A persona file with only one layer present still loads."""
    p = Persona.from_dict({"label": "minimal", "expression": {"directness": 0.9}})
    assert p.label == "minimal"
    assert p.expression.directness == 0.9
    # Other layers fall back to defaults.
    assert isinstance(p.hexaco, HexacoLayer)


def test_persona_from_dict_ignores_unknown_keys() -> None:
    p = Persona.from_dict(
        {
            "label": "x",
            "hexaco": {"openness": 0.6, "not_a_field": 99},
            "made_up_top_level": True,
        }
    )
    assert p.hexaco.openness == 0.6


def test_persona_from_dict_clamps_oor_values() -> None:
    p = Persona.from_dict({"hexaco": {"openness": 5.5}})
    assert p.hexaco.openness == 1.0


def test_persona_from_json_file_round_trip(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "persona.json"
    path.write_text(
        json.dumps(LILITH_DEFAULT_PERSONA.to_dict()), encoding="utf-8"
    )
    loaded = Persona.from_json_file(path)
    assert loaded == LILITH_DEFAULT_PERSONA


def test_persona_from_json_file_missing(tmp_path: pathlib.Path) -> None:
    with pytest.raises(FileNotFoundError):
        Persona.from_json_file(tmp_path / "nope.json")


def test_persona_from_json_file_malformed(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        Persona.from_json_file(path)


def test_persona_from_json_file_non_object(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        Persona.from_json_file(path)


# --- Prompt rendering ------------------------------------------------------


def test_default_persona_renders_substantive_block() -> None:
    block = LILITH_DEFAULT_PERSONA.to_overlay_block()
    assert "# Personality" in block
    assert "# Style" in block
    # Default has some strong domains (technology > 0.6).
    assert "technology" in block


def test_default_persona_block_does_not_redeclare_name() -> None:
    """The persona overlay must not declare 'You are Lilith' — that's
    Identity's job. Otherwise the system prompt double-declares her.
    (Trait sentences like 'You are methodical' are fine — second-person
    descriptions, not identity declarations.)"""
    block = LILITH_DEFAULT_PERSONA.to_overlay_block()
    assert "You are Lilith" not in block


def test_neutral_persona_renders_empty() -> None:
    """All-0.5 sliders, no domain weight > 0.6 → empty overlay block."""
    p = Persona(
        label="neutral",
        hexaco=HexacoLayer(
            openness=0.5,
            conscientiousness=0.5,
            extraversion=0.5,
            agreeableness=0.5,
            neuroticism=0.5,
            honesty_humility=0.5,  # bumped down so this layer is fully neutral
        ),
        special=SpecialLayer(
            strength=0.5,
            perception=0.5,
            endurance=0.5,
            charisma=0.5,
            intelligence=0.5,
            agility=0.5,
            luck=0.5,
        ),
        expression=ExpressionLayer(
            sarcasm=0.5,
            warmth=0.5,
            verbosity=0.5,
            formality=0.5,
            directness=0.5,
            humor=0.5,
            empathy=0.5,
            aggression=0.5,
        ),
        domains=DomainsLayer(
            science=0.5,
            philosophy=0.5,
            technology=0.5,
            art=0.5,
            politics=0.5,
            nature=0.5,
            psychology=0.5,
            combat=0.5,
        ),
    )
    assert p.is_neutral()
    assert p.to_overlay_block() == ""


def test_speech_patterns_render_as_bullets() -> None:
    p = Persona(
        label="rules",
        speech_patterns=("Always cite sources.", "Never apologize for length."),
    )
    block = p.to_overlay_block()
    assert "# Behavioral rules" in block
    assert "- Always cite sources." in block
    assert "- Never apologize for length." in block


def test_backstory_truncates_to_400() -> None:
    p = Persona(label="b", backstory="x" * 500)
    block = p.to_overlay_block()
    # Find the backstory in the output and confirm it was truncated.
    assert "# Backstory" in block
    # The backstory section ends at the next double-newline (or EOF).
    section = block.split("# Backstory")[1].strip()
    assert len(section) == 400


def test_high_directness_expression_makes_block_visible() -> None:
    """Cranking directness past the high band emits a directness
    instruction. Exact wording shifts with the graded-bands rewrite
    (2026-05-08); we assert on the semantic substance instead of a
    single keyword."""
    p = Persona(label="x", expression=ExpressionLayer(directness=0.9))
    block = p.to_overlay_block()
    assert "direct" in block.lower()
    # Graded rendering also surfaces a percentage hint at >=0.7 so the
    # LLM has continuous numeric guidance, not a coarse on/off switch.
    assert "%" in block


# --- load_persona ----------------------------------------------------------


def test_load_persona_default_falls_back_to_constant_when_files_missing() -> None:
    """With both default-resolution files absent (the conftest isolation
    points them at non-existent paths), ``load_persona()`` returns the
    in-code constant. This is the last-resort branch."""
    assert load_persona() is LILITH_DEFAULT_PERSONA


def test_load_persona_default_prefers_user_active_json(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``~/.lilith/profiles/active.json`` exists, it wins over
    bundled and constant. Models the real-user-upgrading-from-V3 case."""
    active = tmp_path / "active.json"
    active.write_text(
        json.dumps({"meta": {"name": "MyTunedLilith"}}),
        encoding="utf-8",
    )
    bundled = tmp_path / "bundled.json"
    bundled.write_text(
        json.dumps({"meta": {"name": "BundledLilith"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("jaeger_os.core.persona._DEFAULT_USER_PERSONA", active)
    monkeypatch.setattr("jaeger_os.core.persona._DEFAULT_BUNDLED_PERSONA", bundled)

    loaded = load_persona()
    assert loaded.label == "MyTunedLilith"


def test_load_persona_default_falls_back_to_bundled(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When user's active.json is absent but bundled lilith.json exists,
    bundled is used."""
    bundled = tmp_path / "bundled.json"
    bundled.write_text(
        json.dumps({"meta": {"name": "BundledLilith"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jaeger_os.core.persona._DEFAULT_USER_PERSONA", tmp_path / "missing.json"
    )
    monkeypatch.setattr("jaeger_os.core.persona._DEFAULT_BUNDLED_PERSONA", bundled)

    loaded = load_persona()
    assert loaded.label == "BundledLilith"


def test_load_persona_default_skips_corrupt_user_json(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt user JSON does not crash the launcher — we silently fall
    through to the bundled persona so the agent still boots."""
    active = tmp_path / "broken.json"
    active.write_text("{ this is not valid json", encoding="utf-8")
    bundled = tmp_path / "bundled.json"
    bundled.write_text(
        json.dumps({"meta": {"name": "BundledLilith"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("jaeger_os.core.persona._DEFAULT_USER_PERSONA", active)
    monkeypatch.setattr("jaeger_os.core.persona._DEFAULT_BUNDLED_PERSONA", bundled)

    loaded = load_persona()
    assert loaded.label == "BundledLilith"


def test_load_persona_from_path(tmp_path: pathlib.Path) -> None:
    custom = Persona(label="research", description="research mode")
    p = tmp_path / "research.json"
    p.write_text(json.dumps(custom.to_dict()), encoding="utf-8")
    loaded = load_persona(p)
    assert loaded == custom
