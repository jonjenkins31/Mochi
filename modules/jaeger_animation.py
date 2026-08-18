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


class OfflineRenderer:
    """Frames on demand, by time, with no node and no clock.

    The offline half of this slot. Every tab subscribes to
    `/act/display/frame` and lets the node do the work, which is right
    for a display and impossible for an EXPORT: a deterministic render
    has to ask for frame 431 directly rather than wait 14.4 seconds for
    it to come round.

    Lives here for the same reason `render()` lives in the TTS binding —
    `core/` is not allowed to name an engine, and should not have to.
    Swap the module in the manifest and the exporter follows it.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = int(width), int(height)
        self._open: dict[Any, Any] = {}
        #: The last frame each clip produced. `next_frame()` returns
        #: None for "nothing new", not for "black" — a still image
        #: emits once and then stops — and a display HOLDS the last
        #: frame until something replaces it.
        self._last: dict[Any, bytes] = {}
        self._table = self._adapter_classes()

    @staticmethod
    def _adapter_classes() -> dict:
        from jaeger_animation.node import AnimationNode

        node = AnimationNode(bus=None, width=1, height=1)
        node.register_default_adapters()
        return {name: type(instance)
                for name, instance in node._adapters.items()}  # noqa: SLF001

    def adapter_for(self, asset: str) -> str:
        """What `auto` means for this file — the ENGINE's answer, not a
        second extension table that could disagree with the display."""
        from jaeger_animation.node import adapter_for_path

        return adapter_for_path(asset)

    def frame(self, asset: str, into_ms: float, *, adapter: str = "auto",
              params: dict | None = None) -> bytes | None:
        """One RGBA frame, `into_ms` into `asset`."""
        if not asset:
            return None
        params = dict(params or {})
        key = (asset, str(sorted(params.items())))
        handle = self._open.get(key)
        if handle is None:
            name = adapter or "auto"
            if name == "auto":
                name = self.adapter_for(asset)
            factory = self._table.get(name)
            if factory is None:
                return None
            handle = factory()
            try:
                handle.open(asset, width=self.width, height=self.height,
                            params=params)
            except Exception:  # noqa: BLE001 — one bad clip, not a bad export
                return None
            self._open[key] = handle
        try:
            produced = handle.next_frame(max(0.0, into_ms / 1000.0))
        except Exception:  # noqa: BLE001
            return self._last.get(key)
        if produced is None:
            return self._last.get(key)
        data = bytes(produced.data)
        self._last[key] = data
        return data

    def close(self) -> None:
        for handle in self._open.values():
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass
        self._open.clear()
        self._last.clear()


def scaling(character: Character) -> str:
    """Pixel art needs nearest-neighbour; anything else destroys it."""
    return character.render.get("scaling", "nearest")


# roots()/project_root() are deliberately NOT exported: they are how
# this imported-module integration finds packs, not something a surface calls.
__all__ = ["SLOT", "PROJECT_CHARACTERS", "Character", "CharacterError",
           "OfflineRenderer",
           "available", "load", "load_path", "play", "play_file", "stop",
           "play_sprite_region", "play_bitmap", "play_command", "scaling"]
