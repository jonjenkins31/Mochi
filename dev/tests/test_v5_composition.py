"""v5 is a composition, and these are the seams that make it one.

Headless: no window, no Qt. What is asserted here is that Mochi owns
no engine code, reads its character from a pack rather than from
source, and drives the face entirely over topics.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = tomllib.loads((ROOT / "jaeger.toml").read_text())


# ── the app owns no engine ───────────────────────────────────────

def test_mochi_never_imports_an_engine():
    """The property the whole design rests on. Import the animation
    module here and the window stops being a subscriber — it becomes a
    second code path that an LED matrix cannot take."""
    forbidden = {"jaeger_animation", "jaeger_ai", "PIL", "numpy"}
    for path in (ROOT / "mochi").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                assert root not in forbidden, (
                    f"{path.name} imports {name} — Mochi composes "
                    f"modules, it does not link against them")


def test_the_face_is_bound_by_slot_not_by_import():
    """Swapping the animation engine must be a manifest edit. A factory
    path here would name one implementation forever."""
    animation = [n for n in MANIFEST["node"] if n["id"] == "animation"][0]
    assert animation.get("slot") == "animation"
    assert not animation.get("factory"), \
        "binding by factory hardcodes which engine fills the slot"


def test_v5_0_ships_no_mind_and_no_microphone():
    """v5.0 is a player. A face that works before a mind that talks."""
    enabled = {n["id"] for n in MANIFEST["node"] if n.get("enabled", True)}
    assert enabled == {"animation"}, f"v5.0 boots more than a face: {enabled}"


def test_the_bus_backend_is_declared_not_wired():
    assert MANIFEST["bus"]["backend"] in ("inproc", "zmq")


def test_it_pins_a_framework_that_has_the_hierarchy():
    """v5 publishes /act/display/play, which does not exist before
    0.10. Pinning lower would install a framework whose contract this
    app's topics are absent from."""
    assert MANIFEST["app"]["requires_framework"] == ">=0.10"


# ── the character carries the persona ────────────────────────────

def _string_literals(path: pathlib.Path) -> set[str]:
    """Every string VALUE in a file, excluding docstrings.

    Checked against the AST rather than the raw text on purpose: a
    docstring explaining that feelings must not be hardcoded contains
    the very words it is warning about, and a substring search cannot
    tell the two apart.
    """
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return {
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in docstrings
    }


def test_the_expression_vocabulary_comes_from_the_pack():
    """Mochi must not contain a list of feelings. The pack declares the
    words; a different character declares different ones and plays
    through the same code."""
    literals: set[str] = set()
    for name in ("character.py", "player.py", "__main__.py"):
        literals |= _string_literals(ROOT / "mochi" / name)
    for word in ("happy", "angry", "crying", "shocked", "unamused", "love"):
        assert word not in literals, (
            f"{word!r} is a literal in Mochi's source — that writes one "
            f"character into the app forever")


@pytest.fixture
def emotes():
    pytest.importorskip("jaeger_animation")
    from mochi import character
    return character.load("emotes")


def test_a_pack_loads_with_its_own_vocabulary(emotes):
    assert emotes.name == "emotes"
    assert emotes.grid == (9, 2)
    assert "happy" in emotes.expression_names
    assert emotes.default_expression == "neutral"


def test_expression_and_mouth_are_two_axes(emotes):
    """Row-major: holding an expression and alternating the mouth row
    IS the talking animation. If both axes collapsed to one index this
    would be 18 unrelated pictures."""
    talking = emotes.cell("happy", "open")
    resting = emotes.cell("happy", "closed")
    assert talking != resting
    assert abs(talking - resting) == emotes.grid[0], \
        "mouth states must differ by exactly one row"


def test_every_declared_expression_resolves(emotes):
    cells = {n: emotes.cell(n) for n in emotes.expression_names}
    assert len(set(cells.values())) == len(cells), "two expressions collide"
    assert max(cells.values()) < emotes.grid[0] * emotes.grid[1]


def test_an_unknown_expression_says_what_the_character_knows(emotes):
    from mochi.character import CharacterError
    with pytest.raises(CharacterError, match="ecstatic"):
        emotes.cell("ecstatic")


def test_play_params_are_what_the_adapter_expects(emotes):
    params = emotes.play_params("happy", "open")
    assert params["grid"] == (9, 2)
    assert isinstance(params["cell"], int)
    assert params["scaling"] == "nearest"


def test_a_missing_pack_names_where_it_looked():
    from mochi.character import CharacterError, load
    with pytest.raises(CharacterError, match="Looked in"):
        load("no-such-character")
