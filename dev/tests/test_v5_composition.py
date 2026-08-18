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

def test_mochi_never_calls_the_render_path():
    """The property the whole design rests on: the window RECEIVES
    frames, it does not ask for them. Import the node or an adapter
    here and the window becomes a second code path an LED matrix
    cannot take.

    Reading the character FORMAT is not that. jaeger_animation.characters
    parses a yaml file and returns a dataclass — no bus, no pixels, no
    engine. Forbidding the whole package (as this test did until
    2026-07-27) is what pushed a 209-line duplicate pack reader into
    this app. The rule protects the render boundary, not the package
    name.

    `modules/<provider>.py` is exempt, as it already is in the sibling
    test above: the slot binding exists to BE the single point of
    contact with one engine. That is what let the offline exporter get
    frames without `core/` ever naming a decoder."""
    forbidden = {
        "jaeger_animation.node": "the animation NODE — subscribe, don't call",
        "jaeger_animation.adapters": "decoders are the engine's business",
        "jaeger_animation.play": "the module's own player",
        "jaeger_ai": "JaegerAI is not a Mochi module yet",
        "PIL": "decoding is the engine's job",
        "numpy": "if the app needs pixels, it is doing the engine's work",
    }
    for d in ("core", "interfaces", "nodes", "modules"):
        for path in (ROOT / d).rglob("*.py"):
            # `modules/<provider>.py` IS the slot's binding — the one
            # file whose job is to be the single point of contact with
            # one engine, and the sibling test above already says so.
            # An OFFLINE render belongs there: an export has no bus and
            # no clock and cannot subscribe its way to frame 431, but
            # `core/` still must not name an engine to get one.
            own = path.stem if path.parent.name == "modules" else ""
            tree = ast.parse(path.read_text())
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            for name in imported:
                if own and name.split(".")[0] == own:
                    continue
                for bad, why in forbidden.items():
                    assert not (name == bad or name.startswith(bad + ".")), (
                        f"{path.name} imports {name} — {why}")


def test_the_face_is_bound_by_slot_not_by_import():
    """Swapping the animation engine must be a manifest edit. A factory
    path here would name one implementation forever."""
    animation = [n for n in MANIFEST["node"] if n["id"] == "animation"][0]
    assert animation.get("slot") == "animation"
    assert not animation.get("factory"), \
        "a factory path hardcodes which engine fills the slot"


def test_the_face_is_required_and_the_voice_is_not():
    """v5.1 adds speech and hearing, and they are OPTIONAL — the app
    boots into a working character with neither installed, which is
    exactly what v5.0 was.

    The distinction is capability, not taste. Mochi without its
    animation module has nothing to show and must fail loudly; Mochi
    without a voice is a character that does not speak."""
    nodes = {n["id"]: n for n in MANIFEST["node"]}
    assert nodes["animation"].get("optional", False) is False, \
        "a face is not optional — a Mochi with nothing to show is broken"
    for node_id in ("audio_io", "tts", "stt"):
        assert nodes[node_id].get("optional") is True, (
            f"{node_id} must be optional, or a user with no voice "
            f"installed cannot run Mochi at all")


def test_llm_waits_for_a_real_module_contract():
    nodes = {n["id"]: n for n in MANIFEST["node"]}
    assert "llm" not in nodes
    assert not (ROOT / "modules" / "jaeger_ai.py").exists()


def test_v5_1_added_no_code_to_the_app():
    """The claim v5.0 made about itself, now checkable: adding speech
    and hearing should be MANIFEST blocks, not app code. core/ is
    still one file, and nothing in it knows what a TTS is.

    ONE exception, and it is the point of the directory:
    `modules/jaeger_kokoro_tts.py` may import `jaeger_kokoro_tts`. That
    file exists to be the single named place a provider is spelled out —
    `modules/jaeger_agent.py` has imported `jaeger_agent.messages` since
    v5.2 for exactly that reason. What must not happen is a SECOND file
    naming the provider, or an integration reaching into a provider that
    is not its namesake, and both are still caught below."""
    import ast

    for path in (list((ROOT / "core").glob("*.py"))
                 + list((ROOT / "interfaces").glob("*.py"))
                 + list((ROOT / "modules").glob("*.py"))):
        # modules/<provider>.py is named after the one package it may name.
        own = path.stem if path.parent.name == "modules" else ""
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if own and name.split(".")[0] == own:
                    continue
                assert not name.startswith(("jaeger_kokoro", "jaeger_whisper")), (
                    f"{path.name} imports {name} — the tabs watch TOPICS; "
                    f"importing an engine makes them stop working when a "
                    f"different one is installed")


def test_every_tab_is_a_pure_subscriber():
    """A tab must work whether its module is installed or not. That is
    only true if it never calls the engine — it watches topics."""
    from interfaces import chat, hearing, voice

    for mod in (voice, hearing, chat):
        src = pathlib.Path(mod.__file__).read_text()
        assert "WATCH" in src, (
            f"{mod.__name__} does not use its module integration's WATCH "
            "list — that integration owns which topics follow the module")
        tree = ast.parse(src)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any(name.startswith("jaeger_kokoro_tts") for name in imported)
        assert not any(name.startswith("jaeger_whisper_stt") for name in imported)


def test_chat_talks_to_the_mind_over_topics_not_to_a_model():
    """Chat became real in v5.2 and the boundary did not move: the tab
    publishes a turn and renders a reply. No provider client, no prompt
    assembled here, no model named. If this file ever imports
    `jaeger_agent` directly it has stopped being a subscriber and
    started being half a brain."""
    from interfaces import chat

    src = pathlib.Path(chat.__file__).read_text()
    assert "modules.jaeger_ai" not in src
    for node in ast.walk(ast.parse(src)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            assert not name.startswith("jaeger_agent"), (
                f"chat.py imports {name} — it must go through "
                f"modules/jaeger_agent.py, the one file allowed to name "
                f"the provider")


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
    for name in ("modules/jaeger_animation.py", "interfaces/player.py", "main.py"):
        literals |= _string_literals(ROOT / name)
    for word in ("happy", "angry", "crying", "shocked", "unamused", "love"):
        assert word not in literals, (
            f"{word!r} is a literal in Mochi's source — that writes one "
            f"character into the app forever")


@pytest.fixture
def emotes():
    pytest.importorskip("jaeger_animation")
    from modules import jaeger_animation as characters
    return characters.load("emotes")








# ── the project is where your stuff is visible ───────────────────

def test_the_pack_reader_comes_from_the_module():
    """The format is the contract between Anima Studio and
    JaegerAnimation; the MODULE owns the reader. An app integration that parsed
    character.yaml itself would be a second copy of that truth, and
    the module's is better — it refuses a `kind` it cannot render
    instead of silently showing nothing.

    Checked by IMPORT, not by text: the docstring naming
    character.yaml contains the word, and a substring search cannot
    tell a reference from a parser.
    """
    import ast
    import inspect

    from jaeger_animation import characters as module_characters
    from modules import jaeger_animation as animation

    assert animation.Character is module_characters.Character

    imported = set()
    for node in ast.walk(ast.parse(inspect.getsource(animation))):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "yaml" not in imported, "the app integration parses the pack format"

def test_a_project_character_shadows_a_bundled_one():
    """What Mochi is FOR: demo packs exported from Anima Studio. Drop a
    folder into characters/ and it plays — and a project copy
    beats the one bundled inside an installed module, so editing it
    means editing files you can see.

    This is the ONLY character behaviour Mochi owns. Reading the
    format, validating it, and turning an expression into adapter
    params are the module's, and it has 30 tests for them."""
    pytest.importorskip("jaeger_animation")
    from modules import jaeger_animation as characters

    loaded = characters.load("emotes")
    assert loaded.root.is_relative_to(ROOT / "characters"), (
        f"loaded the bundled copy at {loaded.root} — a project pack "
        f"must win, or 'edit the character' means editing site-packages")


def test_a_missing_pack_says_where_it_looked():
    """Mochi owns the search order, so Mochi owns this error."""
    from modules.jaeger_animation import CharacterError, load

    with pytest.raises(CharacterError, match="Looked in"):
        load("no-such-character")


def test_packs_are_listed_from_the_filesystem():
    """Installing a pack is copying a folder. No registry, no build
    step, nothing to edit — that is the demo workflow."""
    from modules import jaeger_animation as characters
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

    from modules import jaeger_animation as characters
    for name in characters.__all__:
        if name[0].isupper() or name.isupper():
            continue          # types and constants, used by annotation
        assert name in used, (
            f"characters.{name} is exported and called by nothing — "
            f"either wire it into the app or delete it")


# ── bringup variants ─────────────────────────────────────────────

def _manifest(name):
    return tomllib.loads((ROOT / f"{name}.toml").read_text())


def test_a_variant_is_a_manifest_not_a_flag():
    """A variant that changes a SETTING is a flag. One that changes
    which NODES EXIST is not — a flag would have to reach inside the
    composition and disable something, where a manifest just describes
    a different composition. Same reason ROS ships sim.launch.py beside
    robot.launch.py."""
    real = {n["id"] for n in _manifest("jaeger")["node"]}
    sim = {n["id"] for n in _manifest("sim")["node"]}
    assert "audio_io" in real and "audio_io" not in sim
    assert sim < real, "sim should be a subset of the real composition"


def test_sim_touches_no_hardware():
    """The variant you develop against: opening the mic takes 3.6s,
    needs a permission grant, and a process killed mid-stream can wedge
    CoreAudio. None of that is interesting while working on a tab."""
    sim = _manifest("sim")
    ids = {n["id"] for n in sim["node"]}
    for hardware in ("audio_io", "tts", "stt"):
        assert hardware not in ids, f"sim.toml starts {hardware}"


def test_both_variants_run_the_same_app():
    """If sim drifts from real it stops being a test of the real
    thing. The surface and the face must match."""
    real, sim = _manifest("jaeger"), _manifest("sim")
    assert real["surface"] == sim["surface"]
    face = lambda m: [n for n in m["node"] if n["id"] == "animation"][0]
    assert face(real)["slot"] == face(sim)["slot"]
    assert real["config"]["player"] == sim["config"]["player"]


def test_the_launcher_resolves_a_variant_by_name():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_m", ROOT / "main.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    assert m.resolve_manifest("sim").name == "sim.toml"
    assert m.resolve_manifest("jaeger").name == "jaeger.toml"
    assert m.resolve_manifest("sim.toml").name == "sim.toml"
    assert m.resolve_manifest("nope") is None
