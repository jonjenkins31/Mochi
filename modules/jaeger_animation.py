"""The face — how Mochi uses the animation module.

    slot: animation          jaeger-animation fills it today
    consumes  /act/display/play, /act/display/stop
    produces  /act/display/frame, /act/display/state, /act/display/stats

Everything about this module that is MOCHI-SPECIFIC lives here: where
character packs are looked for, and what "show this expression" means
as a bus command. The engine itself stays generic — it knows sprite
cells and has never heard of "happy".

This file deliberately carries the imported provider's real name. The
manifest still binds its stable ``animation`` slot, while operators can
see immediately that Mochi integrates ``jaeger_animation`` today.
"""

from __future__ import annotations

import pathlib
from collections.abc import Mapping
from typing import Any

from jaeger_animation.characters import (   # the module owns the FORMAT
    BUILTIN_DIR, Character, CharacterError, discover_characters,
    load_character,
)
from jaeger_os import topics

#: The capability jaeger.toml binds. Named here too so this file is a
#: complete answer to "what is the face made of".
SLOT = "animation"

#: Where a pack exported from Anima Studio lands.
PROJECT_CHARACTERS = pathlib.Path("characters")


def project_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def roots() -> tuple[pathlib.Path, ...]:
    """Character roots, in PRECEDENCE-LAST order.

    `discover_characters` builds a dict keyed by name, so a later root
    OVERWRITES an earlier one. Built-ins therefore come first and this
    project's packs last — the reverse of how it reads, which is why
    it is spelled out. Written the intuitive way round the overlay
    silently inverts, and you edit a pack in characters/ while
    the venv copy is what plays.
    """
    return (BUILTIN_DIR, project_root() / PROJECT_CHARACTERS)


def available() -> list[str]:
    """Every playable pack. Installing one is copying a folder."""
    return sorted(discover_characters(roots()))


def load(name: str) -> Character:
    """Load a pack by name, this project's copy winning."""
    found = discover_characters(roots())
    if name not in found:
        raise CharacterError(
            f"no character pack {name!r}. Looked in: "
            f"{', '.join(str(r) for r in roots())}. "
            f"Found: {sorted(found) or 'none'}")
    return found[name]


def load_path(root: pathlib.Path | str) -> Character:
    """Validate and load one pack directly from its editable folder."""
    return load_character(root)


# ── driving it ───────────────────────────────────────────────────

def play(bus: Any, character: Character, expression: str,
         mouth: str = "") -> None:
    """Show a character state using only its manifest declaration.

    ``character/v1`` originally implemented only the common Cartesian
    sprite case (expression column x mouth row). Mochi also accepts the
    other address forms the adapters already understand: a flat cell,
    an irregular source rectangle, a clip selected by state, or params
    for a procedural asset. The artwork's physical layout therefore
    stays in YAML instead of leaking into this dispatcher.
    """
    expr = expression or character.default_expression
    state = mouth or character.default_mouth
    if expr not in character.expressions:
        raise CharacterError(
            f"{character.name}: unknown expression {expr!r}; "
            f"has {sorted(character.expressions)}")

    spec = character.expressions[expr]
    asset = str(spec.get("asset", character.render["asset"]))
    adapter = str(spec.get("adapter", character.adapter))
    params = dict(spec.get("params") or {})

    # Framing is character data, not a preview preference.  Carry it all
    # the way to the media adapter so a wide video character is letterboxed
    # instead of silently stretched square.  character/v1 inherited the v3
    # words: fit=contain, fill=cover, stretch=exact fill.
    framing = str(character.render.get("framing", "fit")).lower()
    params.setdefault("fit", {
        "fit": "contain", "fill": "cover", "stretch": "fill",
    }.get(framing, framing))

    if character.kind == "sprite_sheet":
        if "src" in spec:
            params["src"] = spec["src"]
        elif "cell" in spec:
            params["cell"] = int(spec["cell"])
            params["grid"] = tuple(spec.get("grid") or character.grid or ())
        else:
            params.update(character.play_params(expr, state))
    elif character.kind == "clip_set":
        clips = spec.get("clips")
        if isinstance(clips, Mapping):
            asset = str(clips.get(state) or clips.get("default") or "")
        elif isinstance(clips, str):
            asset = clips
        if not asset:
            raise CharacterError(
                f"{character.name}: expression {expr!r} has no clip for "
                f"state {state!r}")
        params.setdefault("loop", bool(spec.get("loop", True)))
    elif character.kind == "procedural":
        # The adapter owns the parameter vocabulary; the character only
        # names useful presets such as calm, alert, or speaking.
        pass
    else:
        raise CharacterError(
            f"{character.name}: kind {character.kind!r} is not playable "
            "by Mochi's current character dispatcher")

    bus.publish(topics.DisplayCommand(
        adapter=adapter,
        asset_path=str(character.root / asset),
        params=params,
    ))


def play_file(bus: Any, path: pathlib.Path, *, loop: bool = True) -> None:
    """Play any file the engine has an adapter for.

    ``adapter="auto"`` routes by extension INSIDE the engine, so
    nothing here needs to know about decoders — a gif, an mp4 and a
    procedural scene are all just a path.
    """
    params: dict[str, Any] = {"loop": loop}
    if path.suffix.lower() == ".mscript":
        # Character-owned scripts live at
        # characters/<pack>/mscripts/, one level deeper than the
        # legacy assets/mscripts/ directory.  Tell the adapter the stable
        # project root instead of making resource resolution depend on how
        # deeply the script happens to be stored.
        params["asset_root"] = str(project_root())
    bus.publish(topics.DisplayCommand(
        adapter="auto", asset_path=str(path), params=params))


def play_sprite_region(bus: Any, path: pathlib.Path,
                       src: list[int] | tuple[int, int, int, int]) -> None:
    """Render the exact atlas region selected by the Sprite Editor."""
    bus.publish(topics.DisplayCommand(
        adapter="sprite",
        asset_path=str(path),
        params={"src": tuple(int(value) for value in src)},
    ))


def play_bitmap(bus: Any, path: pathlib.Path, *,
                fg_rgb: tuple[int, int, int] = (255, 255, 255),
                bg_rgb: tuple[int, int, int] = (0, 0, 0)) -> None:
    """Render a packed monochrome bitmap selected by Bitmap Editor."""
    bus.publish(topics.DisplayCommand(
        adapter="bitmap",
        asset_path=str(path),
        params={"fg_rgb": tuple(fg_rgb), "bg_rgb": tuple(bg_rgb)},
    ))


def play_command(bus: Any, *, adapter: str, asset_path: str = "",
                 params: dict[str, Any] | None = None,
                 duration_ms: int = 0) -> None:
    """Publish an advanced/raw display command from Runtime Controls."""
    bus.publish(topics.DisplayCommand(
        adapter=adapter or "auto", asset_path=asset_path,
        params=dict(params or {}), duration_ms=max(0, int(duration_ms)),
    ))


def stop(bus: Any) -> None:
    bus.publish(topics.DisplayStop())


def scaling(character: Character) -> str:
    """Pixel art needs nearest-neighbour; anything else destroys it."""
    return character.render.get("scaling", "nearest")


# roots()/project_root() are deliberately NOT exported: they are how
# this imported-module integration finds packs, not something a surface calls.
__all__ = ["SLOT", "PROJECT_CHARACTERS", "Character", "CharacterError",
           "available", "load", "load_path", "play", "play_file", "stop",
           "play_sprite_region", "play_bitmap", "play_command", "scaling"]
