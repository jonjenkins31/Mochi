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
    for d in ("core", "interfaces", "nodes"):
      for path in (ROOT / d).rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root_pkg = name.split(".")[0]
                assert root_pkg not in forbidden, (
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


def test_the_manifest_declares_the_app_FORMAT_not_the_release():
    """These are two axes and conflating them refuses to boot.
    `requires_framework` checks jaeger_os.app.FRAMEWORK_FORMAT — the
    shape of this file — which is 0.1 and moves rarely. The topic
    contract v5 actually needs (0.10, where /act/display/play exists)
    is a DEPENDENCY, pinned in pyproject.toml."""
    from jaeger_os.app import FRAMEWORK_FORMAT

    declared = MANIFEST["app"]["requires_framework"].lstrip(">=")
    assert tuple(int(x) for x in declared.split(".")) <= \
        tuple(int(x) for x in FRAMEWORK_FORMAT.split(".")), (
        f"manifest wants format {declared}, chassis is {FRAMEWORK_FORMAT}")

    reqs = (ROOT / "requirements.txt").read_text()
    assert "jaeger-os" in reqs, \
        "the topic contract must be pinned as a dependency"


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
    for name in ("core/characters.py", "interfaces/player.py",
                 "main.py"):
        literals |= _string_literals(ROOT / name)
    for word in ("happy", "angry", "crying", "shocked", "unamused", "love"):
        assert word not in literals, (
            f"{word!r} is a literal in Mochi's source — that writes one "
            f"character into the app forever")


@pytest.fixture
def emotes():
    pytest.importorskip("jaeger_animation")
    from core import characters
    return characters.load("emotes")


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
    from core.characters import CharacterError
    with pytest.raises(CharacterError, match="ecstatic"):
        emotes.cell("ecstatic")


def test_play_params_are_what_the_adapter_expects(emotes):
    params = emotes.play_params("happy", "open")
    assert params["grid"] == (9, 2)
    assert isinstance(params["cell"], int)
    assert params["scaling"] == "nearest"


def test_a_missing_pack_names_where_it_looked():
    from core.characters import CharacterError, load
    with pytest.raises(CharacterError, match="Looked in"):
        load("no-such-character")


# ── the project is where your stuff is visible ───────────────────

def test_a_project_character_shadows_a_bundled_one():
    """What Mochi is FOR: demo packs exported from Anima Studio. Drop a
    folder into assets/characters/ and it plays — and a project copy
    beats the one bundled inside an installed module, so editing it
    means editing files you can see."""
    pytest.importorskip("jaeger_animation")
    from core import characters

    loaded = characters.load("emotes")
    assert loaded.directory.is_relative_to(ROOT / "assets" / "characters"), (
        f"loaded the bundled copy at {loaded.directory} — a project pack "
        f"must win, or 'edit the character' means editing site-packages")


def test_packs_are_listed_from_the_filesystem():
    """Installing a pack is copying a folder. No registry, no build
    step, nothing to edit — that is the demo workflow."""
    from core import characters
    assert "emotes" in characters.available()


def test_the_project_carries_a_modules_dir():
    """The overlay seam. Empty is the healthy default; what matters is
    that the door exists and is documented, so overriding an engine
    never means editing a venv."""
    modules = ROOT / "modules"
    assert modules.is_dir()
    assert (modules / "README.md").is_file(), \
        "an empty directory with no explanation teaches nobody"


def test_the_surface_lives_in_interfaces():
    """Same shape as JP01-CC01: nodes/ for what the project runs,
    interfaces/ for what an operator looks at."""
    surface = [s for s in MANIFEST["surface"] if s.get("main")][0]
    assert surface["factory"].startswith("interfaces."), surface["factory"]
    assert (ROOT / "interfaces" / "player.py").is_file()


# ── no dead surface ──────────────────────────────────────────────

def test_no_module_is_a_python_package(tmp_path):
    """modules/ is a discovery ROOT — scanned as directories, never
    imported. An __init__.py there says 'package' to a reader and to
    tooling, and means neither."""
    assert not (ROOT / "modules" / "__init__.py").exists()


def test_the_app_version_has_one_home():
    """jaeger.toml carries it. A second copy in core/__init__.py was
    one more thing to forget on a release.

    Checked against the AST: the docstring EXPLAINING that there is no
    __version__ contains the word, and a substring search cannot tell
    an explanation from an assignment."""
    import ast

    assert MANIFEST["app"]["version"]
    tree = ast.parse((ROOT / "core" / "__init__.py").read_text())
    assigned = {
        t.id for node in tree.body if isinstance(node, ast.Assign)
        for t in node.targets if isinstance(t, ast.Name)
    }
    assert "__version__" not in assigned


def test_every_public_helper_is_actually_used():
    """A helper only its own test calls is speculative surface. This
    catches the shape: exported, tested, and reachable from nothing a
    user does."""
    import ast

    used: set[str] = set()
    for d in ("interfaces", "core", "nodes"):
        for path in (ROOT / d).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Attribute):
                    used.add(node.attr)
                elif isinstance(node, ast.Name):
                    used.add(node.id)
    used |= set(ast.parse((ROOT / "main.py").read_text()).body and
                [n.attr for n in ast.walk(ast.parse((ROOT / "main.py").read_text()))
                 if isinstance(n, ast.Attribute)])

    from core import characters
    for name in characters.__all__:
        if name[0].isupper() or name.isupper():
            continue          # types and constants, used by annotation
        assert name in used, (
            f"characters.{name} is exported and called by nothing — "
            f"either wire it into the app or delete it")
