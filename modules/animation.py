"""The face — how Mochi uses the animation module.

    slot: animation          jaeger-animation fills it today
    consumes  /act/display/play, /act/display/stop
    produces  /act/display/frame, /act/display/state, /act/display/stats

Everything about this module that is MOCHI-SPECIFIC lives here: where
character packs are looked for, and what "show this expression" means
as a bus command. The engine itself stays generic — it knows sprite
cells and has never heard of "happy".

TO OVERRIDE THE ENGINE, change this file. Wrap `play()` to add your
own defaults, point `roots()` somewhere else, or swap which slot the
manifest binds. If you need to change the engine's own code, drop a
copy into `modules/animation/` (a directory, with its module.yaml) and
it shadows the installed one — discovery scans directories, so it
ignores this file and finds that.
"""

from __future__ import annotations

import pathlib
from typing import Any

from jaeger_animation.characters import (   # the module owns the FORMAT
    BUILTIN_DIR, Character, CharacterError, discover_characters,
)
from jaeger_os import topics

#: The capability jaeger.toml binds. Named here too so this file is a
#: complete answer to "what is the face made of".
SLOT = "animation"

#: Where a pack exported from Anima Studio lands.
PROJECT_CHARACTERS = pathlib.Path("assets/characters")


def project_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def roots() -> tuple[pathlib.Path, ...]:
    """Character roots, in PRECEDENCE-LAST order.

    `discover_characters` builds a dict keyed by name, so a later root
    OVERWRITES an earlier one. Built-ins therefore come first and this
    project's packs last — the reverse of how it reads, which is why
    it is spelled out. Written the intuitive way round the overlay
    silently inverts, and you edit a pack in assets/characters/ while
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


# ── driving it ───────────────────────────────────────────────────

def play(bus: Any, character: Character, expression: str,
         mouth: str = "") -> None:
    """Show an expression.

    Mechanism, not policy: this says which cell of which atlas, never
    what mood to be in. The character supplies the mapping.
    """
    bus.publish(topics.DisplayCommand(
        adapter=character.adapter,
        asset_path=str(character.asset_path),
        params=character.play_params(expression, mouth),
    ))


def play_file(bus: Any, path: pathlib.Path, *, loop: bool = True) -> None:
    """Play any file the engine has an adapter for.

    ``adapter="auto"`` routes by extension INSIDE the engine, so
    nothing here needs to know about decoders — a gif, an mp4 and a
    procedural scene are all just a path.
    """
    bus.publish(topics.DisplayCommand(
        adapter="auto", asset_path=str(path), params={"loop": loop}))


def stop(bus: Any) -> None:
    bus.publish(topics.DisplayStop())


def scaling(character: Character) -> str:
    """Pixel art needs nearest-neighbour; anything else destroys it."""
    return character.render.get("scaling", "nearest")


# roots()/project_root() are deliberately NOT exported: they are how
# this binding finds packs, not something a surface should call.
__all__ = ["SLOT", "PROJECT_CHARACTERS", "Character", "CharacterError",
           "available", "load", "play", "play_file", "stop", "scaling"]
