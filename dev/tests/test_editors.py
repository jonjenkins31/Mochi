"""The integrated editors preserve the Mochi 3.0 file contracts."""

from __future__ import annotations

import pathlib
import time
from types import SimpleNamespace

import yaml

from interfaces.bitmap_editor import pack_bitmap, unpack_bitmap
from interfaces.character_editor import character_asset_rows
from interfaces.mscript_editor import build_mscript, parse_mscript, parse_resources
from interfaces.modules import module_inventory
from interfaces.sprite_editor import build_sprite_script, parse_sprite_script
from modules import jaeger_animation as animation


ROOT = pathlib.Path(__file__).resolve().parents[2]


class _FakeSession:
    """The engine's two self-speech hooks, which nothing in Mochi called
    until the voice loop started answering itself."""

    def __init__(self) -> None:
        self.paused = False
        self.last_reply_text = ""
        self.followups = 0

    def set_paused(self, paused: bool) -> None:
        self.paused = bool(paused)

    def remember_reply(self, text: str) -> None:
        self.last_reply_text = text

    @property
    def adapter(self):
        return self

    def open_followup(self) -> None:
        self.followups += 1


class _FakeSupervisor:
    """The audio switches talk to the supervisor, not to a widget.

    Enough of ``jaeger_os.app.supervisor.Supervisor`` to prove that:
    starting really means starting a node, and the checkbox reads its
    state back rather than remembering the click.
    """

    def __init__(self, declared: tuple[str, ...] = ("audio_io", "vision")) -> None:
        self.running: set[str] = set()
        self.declared = declared
        self.session = _FakeSession()

    def ls(self) -> list[dict]:
        """What the manual node strip enumerates — the manifest's nodes
        and what the supervisor is doing with each."""
        return [{"id": node_id, "tier": "app", "backend": "inproc",
                 "state": "running" if node_id in self.running else "stopped",
                 "uptime_s": 1.0 if node_id in self.running else 0.0,
                 "restarts": 0}
                for node_id in self.declared]

    def node(self, node_id: str):
        """The live node object, as `Supervisor.node()` hands it over —
        `None` for anything not running, which is what the self-speech
        gate has to cope with every time the microphone is off."""
        return self if node_id in self.running else None

    def has(self, node_id: str) -> bool:
        return True

    def is_running(self, node_id: str) -> bool:
        return node_id in self.running

    def start(self, node_id: str) -> None:
        self.running.add(node_id)

    def stop(self, node_id: str) -> None:
        self.running.discard(node_id)


def test_mscript_sections_and_resources_round_trip():
    text = build_mscript(
        "SPRITE K[1] D[0.5] SRC[1,2,32,32]\nWAIT D[0.5]",
        [("K[1]", "characters/Patric/assets/patric_emotes.bmp")],
        header=["! preserved header"],
    )
    sections = parse_mscript(text)
    assert sections["_header"] == ["! preserved header", ""]
    assert parse_resources(sections["resources"]) == [
        ("K[1]", "characters/Patric/assets/patric_emotes.bmp")]
    assert sections["main"][0].startswith("SPRITE K[1]")


def test_sprite_timeline_round_trip():
    sprites = [[1, 2, 32, 32], [40, 2, 32, 32]]
    timeline = [
        {"cmd": "sprite", "index": 0},
        {"cmd": "delay", "duration": 0.25},
        {"cmd": "sprite", "index": 1},
    ]
    text = build_sprite_script("K[1]", "assets/sheet.png", sprites, timeline)
    resource_id, path, parsed_sprites, parsed_timeline = parse_sprite_script(text)
    assert resource_id == "K[1]"
    assert path == "assets/sheet.png"
    assert parsed_sprites == sprites
    assert parsed_timeline == timeline


def test_legacy_sprite_editor_scripts_point_to_existing_atlases():
    scripts = [
        ROOT / "assets/mscripts/demo_sprite.mscript",
        ROOT / "assets/mscripts/demo_sprite_ Patric Sprite.mscript",
    ]
    for script in scripts:
        _resource_id, image, sprites, timeline = parse_sprite_script(
            script.read_text(encoding="utf-8"))
        assert (ROOT / image).is_file(), script
        assert sprites and timeline


def test_every_character_state_maps_to_an_existing_render_asset():
    kinds = {}
    for name in animation.available():
        character = animation.load(name)
        rows = character_asset_rows(character)
        assert rows, name
        assert all(row["exists"] for row in rows), name
        kinds[name] = (character.kind, character.adapter)

    assert kinds["cat"] == ("sprite_sheet", "sprite")
    assert kinds["bitmap_man"] == ("clip_set", "bitmap")
    assert kinds["mochi"] == ("clip_set", "video")


def test_cat_exposes_generated_and_legacy_sprite_assets():
    path = ROOT / "characters/Cyber Cat/character.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert set(manifest["assets"]) == {"generated", "legacy"}
    for asset in manifest["assets"].values():
        assert (path.parent / asset["file"]).is_file()
        assert (path.parent / asset["properties"]).is_file()


def test_cat_sprite_editor_previews_each_assets_declared_default(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from interfaces.sprite_editor import SpriteEditorTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    previews = []
    editor = SpriteEditorTab(
        None, (QtCore, QtGui, QtWidgets),
        on_preview=lambda path, src: previews.append((path.name, src)),
    )
    try:
        assert editor.load_character(animation.load("cat"))
        assert editor.character_asset_box.currentText() == "generated"
        assert editor.sprite_list.currentRow() == 17
        assert previews[-1] == ("cat.png", [1024, 128, 128, 128])

        editor.character_asset_box.setCurrentText("legacy")
        qt_app.processEvents()
        assert editor.sprite_list.currentRow() == 24
        assert previews[-1] == (
            "1B47E7EA-F50C-47B9-A58B-A426C4CEDEAB_1_105_c.jpeg",
            [29, 777, 86, 79],
        )
    finally:
        editor.close()


def test_every_character_owns_valid_motion_scripts():
    manifests = sorted((ROOT / "characters").glob("*/character.yaml"))
    assert manifests
    for manifest_path in manifests:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        motion = manifest.get("motion_scripts")
        assert motion, manifest_path
        scripts_dir = manifest_path.parent / motion["root"]
        scripts = sorted(scripts_dir.glob("*.mscript"))
        assert scripts, manifest_path
        assert (manifest_path.parent / motion["default"]).is_file()
        for script in scripts:
            sections = parse_mscript(script.read_text(encoding="utf-8"))
            resources = parse_resources(sections.get("resources", []))
            # A script has a [Main] program, or [Track_*] channels, or
            # both. Track-only is a scene authored as a listing — see
            # core/scenes.compile_timeline.
            tracks = [k for k in sections if k.startswith("track_")]
            assert sections.get("main") or tracks, script
            assert resources, script
            for _resource_id, resource in resources:
                assert (ROOT / resource).is_file(), (script, resource)


def test_every_character_folder_is_a_complete_pack():
    folders = sorted(path for path in (ROOT / "characters").iterdir()
                     if path.is_dir())
    assert folders
    for folder in folders:
        assert (folder / "character.yaml").is_file(), folder
        assert (folder / "assets").is_dir(), folder
        assert (folder / "mscripts").is_dir(), folder


def test_character_motion_playback_uses_the_project_as_asset_root():
    published = []

    class Bus:
        def publish(self, message):
            published.append(message)

    script = ROOT / "characters/Cyber Cat/mscripts/talking.mscript"
    animation.play_file(Bus(), script, loop=False)
    assert published[0].params["asset_root"] == str(ROOT)


def test_sprite_region_preview_publishes_the_selected_crop():
    published = []

    class Bus:
        def publish(self, message):
            published.append(message)

    image = ROOT / "characters/Cyber Cat/assets/cat.png"
    animation.play_sprite_region(Bus(), image, [1024, 128, 128, 128])
    assert published[0].adapter == "sprite"
    assert published[0].asset_path == str(image)
    assert published[0].params["src"] == (1024, 128, 128, 128)


def test_module_inventory_uses_the_concrete_imported_provider_name():
    node = SimpleNamespace(
        id="voice", slot="tts", factory="jaeger_kokoro_tts.node:make",
        package="jaeger-kokoro-tts", enabled=True,
    )
    candidate = SimpleNamespace(
        id="org.jenkinsrobotics.tts.kokoro", name="JaegerKokoroTTS",
        type="module", implementation="kokoro",
        module="kokoro_tts", slot="tts",
        factory="jaeger_kokoro_tts.node:make", version="2.0.0",
        source_dir=ROOT.parent / "JaegerKokoroTTS", kind="engine",
        consumes=[], produces=[], tools=[],
    )
    supervisor = SimpleNamespace(ls=lambda: [{"id": "voice", "state": "running"}])
    app = SimpleNamespace(
        spec=SimpleNamespace(nodes=[node]), supervisor=supervisor, root=ROOT)
    rows = module_inventory(app, {"tts": [candidate]})
    assert rows[0]["provider"] == "jaeger_kokoro_tts"
    assert rows[0]["id"] == "org.jenkinsrobotics.tts.kokoro"
    assert rows[0]["name"] == "JaegerKokoroTTS"
    assert rows[0]["implementation"] == "kokoro"
    assert rows[0]["selected"] is True
    assert rows[0]["state"] == "running"


def test_missing_module_inventory_still_shows_its_import_name():
    node = SimpleNamespace(
        id="voice", slot="tts", factory="",
        package="jaeger-kokoro-tts", enabled=True,
    )
    app = SimpleNamespace(
        spec=SimpleNamespace(nodes=[node]), supervisor=None, root=ROOT)
    rows = module_inventory(app, {"tts": []})
    assert rows[0]["provider"] == "jaeger_kokoro_tts"
    assert rows[0]["state"] == "missing"


def test_modules_tab_tick_leaves_an_unchanged_tree_alone(monkeypatch):
    """The 1 s refresh used to clear() the tree on every tick, dropping it
    to zero rows. Qt's accessibility bridge answers an empty model by
    asking for row 0 anyway, so the console filled with
    "Cell requested for row 0 is out of bounds" once a second, forever."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets

    from interfaces.modules import ModulesTab

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    node = SimpleNamespace(
        id="voice", slot="tts", factory="jaeger_kokoro_tts.node:make",
        package="jaeger-kokoro-tts", enabled=True,
    )
    candidate = SimpleNamespace(
        module="kokoro_tts", slot="tts",
        factory="jaeger_kokoro_tts.node:make", version="2.0.0",
        source_dir=ROOT.parent / "JaegerKokoroTTS", kind="engine",
        consumes=[], produces=[], tools=[],
    )
    state = {"value": "running"}
    supervisor = SimpleNamespace(ls=lambda: [{"id": "voice",
                                              "state": state["value"]}])
    app = SimpleNamespace(
        spec=SimpleNamespace(nodes=[node]), supervisor=supervisor, root=ROOT)

    tab = ModulesTab(app, (QtCore, QtGui, QtWidgets))
    tab._timer.stop()
    tab._discovered = {"tts": [candidate]}
    tab.refresh_runtime()
    assert tab.table.topLevelItemCount() == 1

    clears: list[int] = []
    tab.table.clear = lambda: clears.append(1)
    tab.refresh_runtime()
    tab.refresh_runtime()
    assert clears == [], "unchanged inventory still rebuilt the tree"

    # A node changing state is a real change and must still redraw.
    state["value"] = "stopped"
    tab.refresh_runtime()
    assert clears, "a real inventory change was not drawn"


def test_imported_module_integrations_use_provider_filenames():
    expected = {
        "jaeger_animation.py",
        "jaeger_kokoro_tts.py",
        "jaeger_whisper_stt.py",
    }
    assert expected <= {path.name for path in (ROOT / "modules").glob("*.py")}
    assert not {"animation.py", "tts.py", "stt.py"} & {
        path.name for path in (ROOT / "modules").glob("*.py")}


def test_all_legacy_procedural_scenes_render_a_frame():
    from jaeger_animation.adapters import MathAdapter

    scenes = sorted((ROOT / "assets/math").glob("*.py"))
    assert len(scenes) == 26
    for scene in scenes:
        adapter = MathAdapter()
        try:
            adapter.open(str(scene), width=64, height=48, params={})
            frame = adapter.next_frame(0.0)
            assert frame is not None, scene
            assert len(frame.data) == 64 * 48 * 4, scene
        finally:
            adapter.close()


def test_every_global_mscript_resource_uses_a_live_project_path():
    scripts = sorted((ROOT / "assets/mscripts").glob("*.mscript"))
    assert len(scripts) == 17
    for script in scripts:
        sections = parse_mscript(script.read_text(encoding="utf-8"))
        for _key, resource in parse_resources(sections.get("resources", [])):
            assert (ROOT / resource).is_file(), (script, resource)


def test_bitmap_editor_preserves_row_padding_and_msb_order():
    pixels = [
        [True, False, False, False, False, False, False, True, True],
        [False, True, False, True, False, True, False, True, False],
    ]
    packed = pack_bitmap(pixels)
    assert packed == {"width": 9, "height": 2,
                      "data": [0x81, 0x80, 0x55, 0x00]}
    width, height, decoded = unpack_bitmap(packed)
    assert (width, height, decoded) == (9, 2, pixels)


def test_character_framing_reaches_the_media_adapter():
    published = []

    class Bus:
        def publish(self, message):
            published.append(message)

    animation.play(Bus(), animation.load("mochi"), "scene_0", "primary")
    assert published[0].adapter == "video"
    assert published[0].params["fit"] == "contain"


def test_real_legacy_mscript_event_changes_the_keyed_scene():
    from jaeger_animation.adapters import MScriptAdapter

    adapter = MScriptAdapter()
    adapter.open(
        str(ROOT / "assets/mscripts/demo_math_eyes_sequence.mscript"),
        width=128, height=64, params={"asset_root": str(ROOT)})
    try:
        adapter.next_frame(0.0)
        scene = adapter._active._script
        assert scene.is_asleep is True
        # D[11] expires, then the explicit WAIT D[1] begins.
        adapter.next_frame(11.0)
        adapter.next_frame(12.0)
        assert adapter._active._script is scene
        assert scene.is_asleep is False
    finally:
        adapter.close()


def test_window_contains_migrated_editors_and_node_surfaces(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("MOCHI_NO_CYCLE", "1")
    from PySide6 import QtWidgets
    from jaeger_os import InProcBus
    from interfaces.window import MochiWindow

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = SimpleNamespace(
        bus=InProcBus(),
        config={"player": {"character": "emotes", "scale": 1}},
        spec=SimpleNamespace(nodes=[]), supervisor=None, root=ROOT,
    )
    window = MochiWindow(app)
    try:
        tabs = [window.widget.tabText(i) for i in range(window.widget.count())]
        assert tabs == [
            "Face", "Cast", "Characters", "MScript Editor", "Assets", "Modules",
            "Runtime", "Stage", "Windows", "Chat", "Voice", "Hearing", "Vision",
        ]
        assert window.window_manager.popup.player.skins["tv1"].image.is_file()
        window.face.popup_btn.click()
        qt_app.processEvents()
        assert window.window_manager.popup.player.isVisible()
        window.window_manager.popup.player.hide()
        # The Chat tab follows the module, not a hardcoded state: usable
        # when a mind is installed, and explicit about it when not.
        from modules import jaeger_agent as mind
        assert window.chat.entry.isEnabled() is mind.available()
        assert window.chat.state.text().startswith("mind: ")
        # The hidden bitmap editor must still expose a valid table model to
        # macOS accessibility before a bitmap character is selected.
        assert window.character_editor.bitmap_editor.grid.rowCount() == 1
        assert window.character_editor.bitmap_editor.grid.columnCount() == 1
        window.character_editor.select_character("bitmap_man")
        qt_app.processEvents()
        assert window.character_editor.editor_stack.currentWidget() is \
            window.character_editor.bitmap_editor.widget
        assert window.character_editor.bitmap_editor.path.is_file()
        assert window.character_editor.bitmap_editor.grid.isEnabled()
    finally:
        window.close()
        app.bus.close()


def test_window_gallery_only_offers_archives_that_are_still_on_disk():
    """Deleting an archive generation must remove its rows, not break them.

    Every window it listed has a v5 tab, so the gallery is a reference, not
    a dependency: the assertion is that it never offers a launch button for
    a file that is gone.
    """
    from interfaces.legacy_windows import legacy_window_specs

    specs = legacy_window_specs(ROOT)
    assert all(spec.source.is_file() for spec in specs)
    # JaegerAI joined the gallery: a sibling product's UI, offered for
    # review beside what replaced it. Same rule — a row only exists if
    # the thing it launches is on disk.
    assert {spec.generation for spec in specs} <= {
        "Mochi 3.0", "Mochi v4", "JaegerAI"}


def test_every_archived_editor_has_a_live_replacement_tab(monkeypatch):
    """The 3.0 authoring tools survive their archive being deleted."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("MOCHI_NO_CYCLE", "1")
    from PySide6 import QtWidgets
    from jaeger_os import InProcBus
    from interfaces.window import MochiWindow

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = SimpleNamespace(
        bus=InProcBus(),
        config={"player": {"character": "emotes", "scale": 1}},
        spec=SimpleNamespace(nodes=[]), supervisor=None, root=ROOT,
    )
    window = MochiWindow(app)
    try:
        editor = window.character_editor
        # A gif pack selects the asset map, and the sprite and bitmap editors
        # stay reachable anyway — 3.0 launched each as its own script.
        editor.select_character("mochi")
        qt_app.processEvents()
        assert editor.editor_stack.currentWidget() is editor.mapping_editor.widget
        for index, widget in enumerate((editor.sprite_editor.widget,
                                        editor.bitmap_editor.widget,
                                        editor.mapping_editor.widget)):
            editor.editor_box.setCurrentIndex(index)
            qt_app.processEvents()
            assert editor.editor_stack.currentWidget() is widget
            assert editor.pages.tabText(1) == editor.editor_box.itemText(index)
        assert callable(editor.bitmap_editor.open_bitmap)
    finally:
        window.close()
        app.bus.close()


def test_popup_player_restores_skin_and_settings_contract():
    from interfaces.popup_player import discover_skins, load_player_settings

    skins = discover_skins(ROOT)
    assert set(skins) >= {"tv1"}
    assert skins["tv1"].screen_bbox == (425, 289, 150, 150)
    settings = load_player_settings(ROOT)
    assert settings.skin == "tv1"
    assert settings.canvas == (512, 512)
    assert settings.topmost is True


# ── the mind: a chatbot, not an agent ────────────────────────────

def test_mind_topics_match_the_module():
    """The integration copies jaeger-agent's topic strings as literals so
    a surface can name them with the module absent. This is what stops
    that copy from drifting into a tab that subscribes to nothing."""
    from modules import jaeger_agent as mind

    mind.chat_only()
    from jaeger_agent import messages

    assert mind.CHAT_SAY == messages.CHAT_INPUT_TOPIC
    assert mind.CHAT_REPLY == messages.CHAT_REPLY_TOPIC
    assert mind.AGENT_STATE == messages.AGENT_STATE_TOPIC


def test_the_mind_is_asked_for_the_bare_loop():
    """~96 tool schemas are ~15,000 tokens against a 4096-token window.
    Mochi wants a character that answers, not one that runs code."""
    import os
    from modules import jaeger_agent as mind

    previous = os.environ.pop(mind.NO_TOOLS_ENV, None)
    try:
        mind.chat_only()
        assert os.environ[mind.NO_TOOLS_ENV] == "1"
    finally:
        if previous is None:
            os.environ[mind.NO_TOOLS_ENV] = "1"   # the suite runs tool-free
        else:
            os.environ[mind.NO_TOOLS_ENV] = previous


def test_a_blank_model_path_is_resolved_before_boot():
    """The node reads its config once at setup, so an empty `model_path`
    in the manifest has exactly one chance to be filled in."""
    from modules import jaeger_agent as mind

    served = {"provider": "lmstudio", "model": "google/gemma-4-e4b"}
    assert mind.resolve_model(served) == "google/gemma-4-e4b"
    assert "model_path" not in served     # nothing to look for

    pinned = {"provider": "llama_cpp", "model_path": "/models/pinned.gguf"}
    assert mind.resolve_model(pinned) == "/models/pinned.gguf"

    blank = {"provider": "llama_cpp", "model_path": ""}
    assert mind.resolve_model(blank) == mind.find_model()
    assert "model_path" in blank          # always written back


def test_chat_tab_publishes_a_turn_and_renders_the_reply(monkeypatch):
    """The whole integration: publish ChatMessage, render ChatReply.

    Driven with the real module's messages on a real bus, so this fails
    if either topic or field name changes underneath the tab."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus
    from modules import jaeger_agent as mind

    mind.chat_only()
    from jaeger_agent.messages import AgentState, ChatMessage, ChatReply
    from interfaces.chat import ChatTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = InProcBus()
    seen: list[ChatMessage] = []
    bus.subscribe(mind.CHAT_SAY, seen.append)
    tab = ChatTab(SimpleNamespace(bus=bus), (QtCore, QtGui, QtWidgets))
    try:
        tab.entry.setText("hello")
        tab.send()
        deadline = time.time() + 2.0
        while not seen and time.time() < deadline:
            qt_app.processEvents()
        assert [m.text for m in seen] == ["hello"]
        assert seen[0].session == tab.session

        bus.publish(AgentState(state="thinking", session=tab.session))
        bus.publish(ChatReply(text="hi there", session=tab.session))
        deadline = time.time() + 2.0
        while "hi there" not in tab.log.toPlainText() and time.time() < deadline:
            tab._drain()
            qt_app.processEvents()
        assert "you: hello" in tab.log.toPlainText()
        assert "mochi: hi there" in tab.log.toPlainText()

        # A new conversation is a new session id, not a cleared widget —
        # otherwise the model still remembers what the log stopped showing.
        before = tab.session
        tab.new_conversation()
        assert tab.session != before
    finally:
        tab.close()
        bus.close()


def test_the_manifest_binds_the_mind_by_slot_and_never_by_name():
    """Swapping brains must stay an install, not an edit."""
    import tomllib

    manifest = tomllib.loads((ROOT / "jaeger.toml").read_text())
    mind_node = [n for n in manifest["node"] if n["id"] == "mind"][0]
    assert mind_node["slot"] == "mind"
    assert "factory" not in mind_node
    assert mind_node["optional"] is True   # no brain is still a character
    assert manifest["config"]["mind"]["provider"] == "llama_cpp"


# ── the node view is the same document ───────────────────────────

def test_every_script_survives_a_trip_through_the_nodes():
    """The node view is a RENDERING, not an importer. Open any script,
    look at it as nodes, save: byte for byte the same file. Anything
    less and switching views silently rewrites the author's work —
    comments, spacing, and commands this app has never heard of."""
    from interfaces.mscript_editor import build_steps, parse_mscript, parse_steps

    scripts = (sorted((ROOT / "assets/mscripts").glob("*.mscript"))
               + sorted((ROOT / "characters").rglob("*.mscript")))
    assert scripts, "no motion scripts to check"
    for path in scripts:
        sections = parse_mscript(path.read_text())
        # every section that holds steps, not just [Main] — a track is
        # steps too, and must survive the node view identically
        for name, body in sections.items():
            if name != "main" and not name.startswith("track_"):
                continue
            assert build_steps(parse_steps(body)) == "\n".join(body), \
                f"{path.name} [{name}] changed just by being looked at"


def test_a_comment_is_a_step_and_not_a_command():
    """Dropping notes and blank lines would be the easy way to build
    this, and it loses exactly what an operator wrote for themselves."""
    from interfaces.mscript_editor import build_steps, parse_steps

    steps = parse_steps(["! why this exists", "", "BITMAP K[1] D[1.0]"])
    assert [s.is_note for s in steps] == [True, True, False]
    assert steps[2].command == "BITMAP"
    assert steps[2].args == {"K": "1", "D": "1.0"}
    assert build_steps(steps) == "! why this exists\n\nBITMAP K[1] D[1.0]"


def test_a_jump_step_resolves_the_label_it_names():
    """`LBL[1:top]` and `JMP LBL[1]` are the same label — the name is a
    comment, and the engine strips it. If the graph did not, the wire
    between a loop's two ends would never be drawn."""
    from interfaces.mscript_editor import parse_steps

    top, jump, other = parse_steps(["LBL[1:top]", "JMP LBL[1]", "WAIT D[1.0]"])
    assert top.label() == jump.label() == 1
    assert other.label() is None


def test_a_step_rewritten_by_the_form_stays_playable():
    """Editing an argument regenerates the line, so the spelling it
    produces has to be the spelling the engine parses."""
    from interfaces.mscript_editor import Step, parse_steps, render_step

    assert render_step("BITMAP", {"K": "1", "D": "2.0"}) == "BITMAP K[1] D[2.0]"
    # LBL carries its id on the command token; JMP takes it as an argument.
    assert render_step("LBL", {"LBL": "1:top"}) == "LBL[1:top]"
    assert render_step("JMP", {"LBL": "1"}) == "JMP LBL[1]"
    step = Step(command="WAIT", args={"D": "1.0"}, raw="WAIT D[1.0]")
    step.retype("WAIT", {"D": "0.25"})
    assert parse_steps([step.raw])[0].args == {"D": "0.25"}


def test_the_nodes_and_the_text_are_one_document(monkeypatch):
    """Two views, one buffer. An edit made as nodes has to arrive in the
    text the Save button writes — otherwise the graph is a toy beside
    the real editor."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus
    from interfaces.mscript_editor import MscriptEditorTab

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = MscriptEditorTab(SimpleNamespace(bus=InProcBus()),
                           (QtCore, QtGui, QtWidgets))
    tab.load_path(ROOT / "assets/mscripts/demo_wink.mscript")
    before = tab.editor.toPlainText()

    tab.show_view(1)
    assert len(tab.graph._items) == len(before.splitlines())
    assert not tab.editor.document().isModified(), \
        "merely opening the node view modified the document"

    tab.graph.palette_box.setCurrentText("JMP")
    tab.graph.add_step()
    assert tab.editor.document().isModified()
    assert tab.editor.toPlainText().splitlines()[-1] == "JMP LBL[1]"


# ── the voice loop must not answer itself ────────────────────────

def _voice_tab(monkeypatch, mode="assistant"):
    """A Chat tab with the ears and the voice both running."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus
    from modules import jaeger_agent as mind
    from interfaces.chat import ChatTab

    mind.chat_only()
    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = InProcBus()
    app = SimpleNamespace(
        bus=bus, supervisor=_FakeSupervisor(),
        config={"voice": {"mode": mode}, "stt": {}, "tts": {},
                "audio_io": {"capture": False}})
    tab = ChatTab(app, (QtCore, QtGui, QtWidgets))
    for box in (tab.mic, tab.speak):
        box.setChecked(True)
    deadline = time.time() + 3.0
    while not (tab._mic_on and tab._speak_replies) and time.time() < deadline:
        tab._drain(); qt_app.processEvents()
    return tab, app, bus, qt_app


def test_the_character_does_not_answer_its_own_voice(monkeypatch):
    """The bug this was written for: reply plays, the mic hears it, the
    STT transcribes it, the mind answers THAT, forever.

    The reply is spoken, the speaker reports playing, and a transcript
    of our own words arrives while it is. It must not become a turn."""
    from jaeger_os import topics
    from jaeger_agent.messages import ChatReply
    from modules import jaeger_agent as mind

    tab, app, bus, qt_app = _voice_tab(monkeypatch)
    turns: list = []
    bus.subscribe(mind.CHAT_SAY, turns.append)
    try:
        bus.publish(ChatReply(text="I am Mochi.", session=tab.session))
        deadline = time.time() + 2.0
        while not app.supervisor.session.last_reply_text and time.time() < deadline:
            tab._drain(); qt_app.processEvents()

        # Both engine-side defences were handed what they needed.
        assert app.supervisor.session.last_reply_text == "I am Mochi.", \
            "the self-speech filter was never told what we said"
        assert app.supervisor.session.paused is True, \
            "the ears stayed open while the character was talking"

        bus.publish(topics.SpeakerState(state="playing"))
        bus.publish(topics.Transcript(text="I am Mochi.", is_final=True))
        deadline = time.time() + 1.0
        while time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert turns == [], f"the character answered itself: {turns}"
        assert "ignored while speaking" in tab.log.toPlainText()
    finally:
        tab.close(); bus.close()


def test_the_ears_reopen_once_the_reply_has_finished(monkeypatch):
    """Deaf forever is the other way to fail. The speaker going idle
    starts a short tail — the VAD's own hangover can still be holding
    our tail — and then real speech gets through again."""
    from jaeger_os import topics
    from jaeger_agent.messages import ChatReply
    from modules import jaeger_agent as mind

    tab, app, bus, qt_app = _voice_tab(monkeypatch)
    turns: list = []
    bus.subscribe(mind.CHAT_SAY, turns.append)
    try:
        bus.publish(ChatReply(text="hello", session=tab.session))
        bus.publish(topics.SpeakerState(state="playing"))
        deadline = time.time() + 2.0
        while not app.supervisor.session.paused and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert app.supervisor.session.paused is True

        # Wait out the real tail. Poking `_deaf_until` from here races
        # the bus thread, which sets it when it processes this message —
        # and losing that race is how the test lied about the code.
        bus.publish(topics.SpeakerState(state="idle"))
        deadline = time.time() + 5.0
        while app.supervisor.session.paused and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert app.supervisor.session.paused is False, "the ears never reopened"
        # And a conversation does not need "hey mochi" in front of every
        # sentence — reopening the ears opens the follow-up window too.
        assert app.supervisor.session.followups == 1

        bus.publish(topics.Transcript(text="what time is it", is_final=True))
        deadline = time.time() + 2.0
        while not turns and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert [m.text for m in turns] == ["what time is it"]
    finally:
        tab.close(); bus.close()


def test_each_pipeline_configures_the_engine_that_implements_it():
    """A mode is settings, not a second implementation — and the two
    settings that stop the loop must actually be in there. Both were
    available and neither was on, which is why it looped."""
    from core import voice_modes

    assert set(voice_modes.names()) == {"assistant", "chat"}

    config: dict = {}
    voice_modes.apply(config, "assistant")
    stt = config["stt"]
    assert stt["require_wake_word"] is True
    assert stt["self_speech_filter"] is True
    assert any("mochi" in phrase for phrase in stt["wake_phrases"])
    assert stt["followup_window_s"] == 10.0        # voice_assistant.py
    assert voice_modes.setting(config, "pause_mic_while_speaking") is True
    assert config["voice"]["mode"] == "assistant"

    voice_modes.apply(config, "chat")
    stt = config["stt"]
    assert stt["require_wake_word"] is False       # every phrase is a turn
    assert stt["barge_in"] is True                 # talk over the reply
    assert config["audio_io"]["aec"] is True       # ...which needs this
    # Switching back must not leave the previous mode's wake phrases
    # behind — a stale list is a wake word nobody thinks is enabled.
    voice_modes.apply(config, "assistant")
    assert config["stt"]["barge_in"] is False


def test_full_duplex_says_so_when_it_cannot_cancel_the_echo():
    """`chat` keeps a live mic beside a playing speaker. Without an echo
    canceller it does not degrade politely, it loops — so it has to say
    so rather than look like it is working."""
    from core import voice_modes
    from core.module_support import installed

    assert voice_modes.warning("assistant") == ""
    warning = voice_modes.warning("chat")
    if installed(voice_modes.AEC_PACKAGE):
        assert warning == ""
    else:
        assert voice_modes.AEC_PACKAGE in warning


def test_mochi_boots_as_a_messaging_llm():
    """Off means not started, not muted.

    The three audio nodes are DECLARED — the switches need a handle to
    start — and disabled, so a launch that only wants to type opens no
    device and loads no model. Deleting the `enabled` keys would make
    the Chat switches lie the moment the app boots with them already on.
    """
    import tomllib

    manifest = tomllib.loads((ROOT / "jaeger.toml").read_text())
    nodes = {n["id"]: n for n in manifest["node"]}
    for node_id in ("audio_io", "tts", "stt"):
        assert nodes[node_id]["enabled"] is False, (
            f"{node_id} starts at boot — a text conversation should not "
            f"cost a model load or a recording indicator")
    assert nodes["mind"].get("enabled", True) is True, \
        "the mind is what a messaging LLM IS — it starts"


def test_the_mic_switch_starts_the_ears_and_routes_what_they_hear(monkeypatch):
    """Both halves, because either one alone is a dead switch: the mic
    box starts the driver AND the engine, and heard speech becomes the
    same turn typing produces. Partials are not turns — the streaming
    pipelines publish them mid-sentence."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus, topics
    from modules import jaeger_agent as mind

    mind.chat_only()
    from interfaces.chat import ChatTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = InProcBus()
    turns: list = []
    bus.subscribe(mind.CHAT_SAY, turns.append)
    app = SimpleNamespace(bus=bus, supervisor=_FakeSupervisor(),
                          config={"stt": {}, "audio_io": {"capture": False}})
    tab = ChatTab(app, (QtCore, QtGui, QtWidgets))
    try:
        assert tab._mic_on is False, "the mic is on at boot"
        tab.mic.setChecked(True)
        deadline = time.time() + 2.0
        while not tab._mic_on and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert tab._mic_on is True
        # The engine consumes /sense/mic/pcm; without the driver — and
        # without the driver CAPTURING — it starts cleanly and hears
        # nothing at all.
        assert app.supervisor.running == {"audio_io", "stt"}
        assert app.config["audio_io"]["capture"] is True

        bus.publish(topics.Transcript(text="still talk", is_final=False))
        bus.publish(topics.Transcript(text="hello there", is_final=True))
        deadline = time.time() + 2.0
        while not turns and time.time() < deadline:
            qt_app.processEvents()
        assert [m.text for m in turns] == ["hello there"]

        # Unticking stops the ROUTING and leaves the ears running: power
        # and routing are different questions, and someone may be
        # watching transcripts in the Hearing tab.
        turns.clear()
        tab.mic.setChecked(False)
        deadline = time.time() + 2.0
        while tab._mic_on and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert app.supervisor.running == {"audio_io", "stt"}, \
            "unticking a routing box powered a node off"
        bus.publish(topics.Transcript(text="not for the mind", is_final=True))
        deadline = time.time() + 1.0
        while time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert turns == [], "routing was off and the mind was asked anyway"

        # Turning them OFF is the Hearing tab's switch, and nothing else
        # wants audio, so the device goes too — "off" that leaves an
        # input stream open is not off.
        from core import audio_switch

        assert audio_switch.switch(app, ears=False) == ""
        assert app.supervisor.running == set()
    finally:
        tab.close()
        bus.close()


# ── the eyes ─────────────────────────────────────────────────────

# ── a character is one folder, two halves ────────────────────────

def test_a_character_pack_carries_both_halves():
    """Looks-and-moves and speaks are one identity, so they are one
    file. The render half is JaegerAnimation's and it ignores the rest,
    which is what lets them share a character.yaml."""
    import yaml
    from core import persona

    sheet = yaml.safe_load(
        (ROOT / "characters/mochi/character.yaml").read_text(encoding="utf-8"))
    # the render half — still valid to the engine that owns it
    assert sheet["kind"] == "clip_set"
    assert sheet["render"]["adapter"] == "video"
    # the speaking half
    assert sheet["identity"]["voice_id"]
    assert sheet["prompt"]["custom_instructions"]
    assert persona.read(ROOT / "characters/mochi")["identity"]

    # and the engine still loads it, which is the whole point of merging
    # into one file rather than inventing a second one beside it
    assert animation.load("mochi").kind == "clip_set"


def test_the_sliders_were_not_imported():
    """HEXACO/SPECIAL/Expression/Domains are weights for a net that was
    trained on them, and inert as prompt text — ~1,800 characters a turn
    buying nothing. They stay in JaegerAI where they mean something."""
    import yaml

    sheet = yaml.safe_load(
        (ROOT / "characters/mochi/character.yaml").read_text(encoding="utf-8"))
    assert "traits" not in sheet
    composed = " ".join(
        (ROOT / "core/persona.py").read_text().split())
    for slider in ("hexaco", "special", "openness", "conscientiousness"):
        assert slider not in composed.lower() or "not imported" in composed.lower()


def test_the_persona_boundary_ships_with_the_voice():
    """Measured in JaegerAI: traits in the execution context drift tool
    arguments toward 'in character' instead of literal. Mochi has no
    tools switched on today, which is exactly why the rule has to be
    there before it does."""
    from core import persona

    composed = persona.compose(persona.read(ROOT / "characters/mochi"))
    assert persona.PERSONA_BOUNDARY in composed
    assert "tool argument" in composed
    # spoken, because the replies go through a synthesiser
    assert "never use emoji" in composed


def test_a_pack_with_no_persona_keeps_the_manifest_prompt(tmp_path):
    """A face with no voice is a valid character. Adding one must be
    opt-in per pack, not a thing that blanks the manifest.

    Synthetic rather than a real pack on purpose: every pack in the
    repo has a voice now, so pointing at one would make this pass for
    the wrong reason the moment that stopped being true."""
    from core import persona

    voiceless = tmp_path / "voiceless"
    voiceless.mkdir()
    (voiceless / "character.yaml").write_text(
        "schema: character/v1\ncharacter: voiceless\nname: Voiceless\n")

    config = {"mind": {"system_prompt": "from the manifest"}}
    assert persona.resolve(config, voiceless) == "from the manifest"
    assert config["mind"]["system_prompt"] == "from the manifest"

    config = {"mind": {"system_prompt": "from the manifest"}}
    resolved = persona.resolve(config, ROOT / "characters/mochi")
    assert "childlike" in resolved
    assert config["mind"]["system_prompt"] == resolved


def test_a_half_written_character_costs_nothing():
    """An empty section must not become a header with nothing under it."""
    from core import persona

    bare = persona.compose({"id": "x", "name": "Rex",
                            "identity": {"role": "a test"}}, spoken=False)
    assert bare.startswith("You are Rex, a test.")
    assert "Speech habits" not in bare
    assert persona.PERSONA_BOUNDARY in bare
    assert persona.compose({}) .count("\n\n") == 1   # style + boundary only


def test_the_camera_is_a_factory_not_a_slot():
    """A slot exists so an ENGINE can be swapped. Opening a webcam is
    `cv2.VideoCapture(0)` and the framework ships the node, so a slot
    here would have exactly one possible occupant. Inference is the
    thing that will deserve one, and it arrives as a separate node on
    /sense/vision/analysis without touching this one."""
    import tomllib

    manifest = tomllib.loads((ROOT / "jaeger.toml").read_text())
    vision = {n["id"]: n for n in manifest["node"]}["vision"]
    assert "slot" not in vision, "vision has one implementation, not a choice"
    assert vision["factory"].startswith("jaeger_os.nodes.vision")
    assert vision["optional"] is True   # a Mochi with no camera still runs
    assert vision["enabled"] is False, \
        "the webcam opens when asked for, not because the app launched"


def test_the_vision_factory_builds_both_generic_sources():
    """The manifest can only name a `(bus, config)` callable, and the
    node takes a constructed adapter — this is the piece that was
    missing, so a typo in `source` has to fail loudly rather than
    quietly booting the wrong camera."""
    import pytest
    from jaeger_os import InProcBus
    from jaeger_os.nodes.vision import (
        TCPCameraAdapter, USBCameraAdapter, make_vision_node)

    bus = InProcBus()
    try:
        usb = make_vision_node(bus, {"source": "usb", "device_index": 2})
        assert isinstance(usb.adapter, USBCameraAdapter)
        tcp = make_vision_node(bus, {"source": "tcp", "port": 9002})
        assert isinstance(tcp.adapter, TCPCameraAdapter)
        assert isinstance(make_vision_node(bus, {}).adapter, USBCameraAdapter)
        with pytest.raises(ValueError) as exc:
            make_vision_node(bus, {"source": "webcam"})
        assert "usb, tcp" in str(exc.value)
    finally:
        bus.close()


def test_the_vision_tab_draws_what_the_camera_publishes(monkeypatch):
    """No OpenCV here and no decoding — the tab hands encoded bytes to
    Qt. If it ever grows a decoder it has become a second engine."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus, topics
    from interfaces.vision import VisionTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    # A real JPEG, made by Qt rather than shipped as a fixture.
    source = QtGui.QImage(64, 48, QtGui.QImage.Format_RGB32)
    source.fill(QtGui.QColor("#4a7ab0"))
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    source.save(buffer, "JPG")
    jpeg = bytes(buffer.data())

    bus = InProcBus()
    app = SimpleNamespace(bus=bus, supervisor=_FakeSupervisor(),
                          config={"vision": {"device_index": 0}})
    tab = VisionTab(app, (QtCore, QtGui, QtWidgets))
    try:
        app.supervisor.running.add("vision")
        bus.publish(topics.CameraFrame(
            image_w=64, image_h=48, encoding="jpeg", frame_bytes=jpeg))
        deadline = time.time() + 2.0
        while not tab._frames and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        tab._drain()
        assert tab._frames == 1
        assert not tab.preview.pixmap().isNull(), "the frame was not drawn"
        assert "live" in tab.status.text()

        # A raw frame has no container for Qt to read. Saying so beats a
        # black rectangle that looks like a dead camera.
        bus.publish(topics.CameraFrame(
            image_w=64, image_h=48, encoding="raw_bgr8", frame_bytes=b"\x00" * 96))
        deadline = time.time() + 2.0
        while tab._frames < 2 and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        tab._drain()
        assert "no preview" in tab.preview.text()
    finally:
        tab.close(); bus.close()


def test_capture_writes_the_bytes_the_camera_produced(monkeypatch, tmp_path):
    """A still is what everything downstream of a camera actually takes —
    a VLM wants a path, an analysis node wants one frame. Saved as the
    sensor encoded it, not re-encoded from the preview, or what gets
    looked at is whatever fitted in a label."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus, topics
    from interfaces.vision import VisionTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    source = QtGui.QImage(32, 24, QtGui.QImage.Format_RGB32)
    source.fill(QtGui.QColor("#c08a3e"))
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    source.save(buffer, "JPG")
    jpeg = bytes(buffer.data())

    bus = InProcBus()
    app = SimpleNamespace(bus=bus, supervisor=_FakeSupervisor(), config={"vision": {}})
    tab = VisionTab(app, (QtCore, QtGui, QtWidgets))
    tab.project_root = tmp_path          # don't litter the repo
    try:
        assert tab.capture() == "", "captured a frame that never arrived"

        app.supervisor.running.add("vision")
        bus.publish(topics.CameraFrame(
            image_w=32, image_h=24, encoding="jpeg", frame_bytes=jpeg))
        deadline = time.time() + 2.0
        while not tab._frames and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        tab._drain()                     # the paint consumes _frame…

        saved = pathlib.Path(tab.capture())   # …and Capture still works
        assert saved.is_file() and saved.suffix == ".jpg"
        assert saved.read_bytes() == jpeg, "the still was re-encoded"
    finally:
        tab.close(); bus.close()


def test_choosing_a_camera_writes_what_the_node_is_built_from():
    """`device_index` is read when the node is BUILT, so the picker has
    to write the live config slice — the copy `settings()` hands out
    would be a camera choice that never reaches a camera."""
    from types import SimpleNamespace as NS
    from core.module_support import VISION_NODE, settings

    app = NS(config={"vision": {"device_index": 0}})
    (app.config or {}).setdefault(VISION_NODE, {})["device_index"] = 1
    assert settings(app, VISION_NODE)["device_index"] == 1


def test_nothing_a_listener_cannot_hear_reaches_the_synthesiser():
    """A model writes for a reader unless told otherwise, and Kokoro
    does not silently skip what it cannot say — it stumbles. "Hello! 😊"
    came out with a noise on the end, which is the bug this fixes."""
    from jaeger_os import InProcBus, topics
    from modules.jaeger_kokoro_tts import say, speakable

    assert speakable("Hello there! I'm Mochi 😊") == "Hello there! I'm Mochi"
    assert speakable("- **one**\n- two\n\nRun `ls` for that.") \
        == "one two Run ls for that."
    assert speakable("## Title\n1. first  🎉🚀") == "Title first"
    # Punctuation is prosody — stripping it makes one long word.
    assert speakable("Wait... really? Yes, 3.5 seconds!") \
        == "Wait... really? Yes, 3.5 seconds!"
    # An answer that was ONLY an emoji has nothing to say.
    assert speakable("👍") == ""

    # And it is cleaned at the choke point, not at each caller.
    bus = InProcBus()
    said: list = []
    bus.subscribe(topics.ACT_SPEECH_SAY, said.append)
    try:
        say(bus, "Sure! 🎉 Here you go.")
        deadline = time.time() + 2.0
        while not said and time.time() < deadline:
            time.sleep(0.01)
        assert [m.text for m in said] == ["Sure! Here you go."]
    finally:
        bus.close()


def test_the_model_is_told_not_to_write_for_a_reader():
    """Stripping emoji is a repair. A prompt that asks for spoken
    English means the repair has nothing left to do."""
    import tomllib

    prompt = tomllib.loads((ROOT / "jaeger.toml").read_text())["config"]["mind"][
        "system_prompt"].lower()
    assert "emoji" in prompt and "markdown" in prompt
    assert "spoken" in prompt or "out loud" in prompt


def test_the_ears_and_the_voice_switch_independently():
    """The whole point of the split: run the STT to watch transcripts
    with no voice, or the TTS to try a Kokoro voice with no microphone
    in the room. Neither needs the mind, and the shared driver has to
    follow whatever is left."""
    from core import audio_switch

    app = SimpleNamespace(supervisor=_FakeSupervisor(),
                          config={"stt": {}, "tts": {}, "audio_io": {}})

    assert audio_switch.switch(app, voice=True) == ""
    assert app.supervisor.running == {"audio_io", "tts"}
    assert audio_switch.state(app) == (False, True)
    # A voice with no ears must not open an input stream.
    assert app.config["audio_io"]["capture"] is False

    # Adding the ears reshapes the driver rather than fighting over it.
    assert audio_switch.switch(app, ears=True) == ""
    assert app.supervisor.running == {"audio_io", "stt", "tts"}
    assert app.config["audio_io"]["capture"] is True

    # `None` means "leave that one alone" — dropping the voice must not
    # take the ears with it, nor close a microphone still in use.
    assert audio_switch.switch(app, voice=False) == ""
    assert audio_switch.state(app) == (True, False)
    assert app.config["audio_io"]["capture"] is True
    assert "audio_io" in app.supervisor.running

    assert audio_switch.switch(app, ears=False) == ""
    assert app.supervisor.running == set(), "the device outlived both engines"


def test_speakers_alone_never_open_the_microphone(monkeypatch):
    """The two switches exist to be independent. A driver that captures
    because a REPLY needs playing is a recording indicator nobody asked
    for, and the surest way to make "mic off" untrue."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus
    from modules import jaeger_agent as mind

    mind.chat_only()
    from interfaces.chat import ChatTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = InProcBus()
    app = SimpleNamespace(bus=bus, supervisor=_FakeSupervisor(),
                          config={"tts": {}, "audio_io": {"capture": False}})
    tab = ChatTab(app, (QtCore, QtGui, QtWidgets))
    try:
        tab.speak.setChecked(True)
        deadline = time.time() + 2.0
        while not tab._speak_replies and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert app.supervisor.running == {"audio_io", "tts"}
        assert app.config["audio_io"]["capture"] is False, \
            "turning the speakers on opened the microphone"
    finally:
        tab.close()
        bus.close()


def test_the_pipelines_offered_are_the_ones_the_module_has():
    """The Hearing tab lists the STT module's own registry rather than a
    copy, and swapping writes the key the node is REBUILT from — the
    mode is read once, at construction, so nothing else would take."""
    from modules import jaeger_whisper_stt as stt

    names = [name for name, _ in stt.modes()]
    if names:      # the module is optional; with it absent the tab greys out
        from jaeger_whisper_stt.engine.registry import METHODS
        assert names == list(METHODS)
        assert all(desc for _, desc in stt.modes()), \
            "a mode with no description is a picker entry nobody can choose"

    app = SimpleNamespace(config={"stt": {"stt_mode": "two_pass"}})
    assert stt.mode(app) == "two_pass"
    assert stt.set_mode(app, "local_agreement") == ""   # ears off: config only
    assert app.config["stt"]["stt_mode"] == "local_agreement"
    assert stt.mode(app) == "local_agreement"


def test_the_voice_rides_the_request_instead_of_a_restart():
    """Kokoro has one synthesis path and many voices, so choosing one
    must not reload 82M parameters. Both tabs read the same config key,
    which is why the Voice tab's picker changes what Chat says too."""
    from jaeger_os import InProcBus, topics
    from modules import jaeger_kokoro_tts as tts

    bus = InProcBus()
    said: list = []
    bus.subscribe(topics.ACT_SPEECH_SAY, said.append)
    app = SimpleNamespace(config={"tts": {}})
    try:
        assert tts.voice(app) == ""            # empty = the module's default
        tts.set_voice(app, "bm_george")
        tts.say(bus, "hello", voice=tts.voice(app))
        deadline = time.time() + 2.0
        while not said and time.time() < deadline:
            time.sleep(0.01)
        assert [(m.text, m.voice) for m in said] == [("hello", "bm_george")]
    finally:
        bus.close()


def test_a_reply_that_never_speaks_says_so(monkeypatch):
    """Kokoro can synthesise fine while nothing plays — no audio_io
    driver means /act/speaker/pcm is published to an empty room. That
    used to be pure silence, which reads as a broken checkbox."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus, topics
    from modules import jaeger_agent as mind
    from modules import jaeger_kokoro_tts as tts

    mind.chat_only()
    from jaeger_agent.messages import ChatReply
    from interfaces.chat import ChatTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = InProcBus()
    asked: list = []
    bus.subscribe(topics.ACT_SPEECH_SAY, asked.append)
    app = SimpleNamespace(bus=bus, supervisor=_FakeSupervisor(), config={"tts": {}})
    tab = ChatTab(app, (QtCore, QtGui, QtWidgets))
    try:
        # The Speakers box is a real switch: it starts the tts node and
        # only then mirrors, so the bool follows the SUPERVISOR rather
        # than the click. Starting happens off the GUI thread.
        tab.speak.setChecked(True)
        deadline = time.time() + 2.0
        while not tab._speak_replies and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert tab._speak_replies is True
        assert "tts" in app.supervisor.running

        bus.publish(ChatReply(text="hello", session=tab.session))
        deadline = time.time() + 2.0
        while not asked and time.time() < deadline:
            qt_app.processEvents()
        assert [m.text for m in asked] == ["hello"], "the reply was not spoken"

        # What the dead speaker path actually publishes.
        bus.publish(topics.SpokenAck(ok=False, duration_s=11.7,
                                     reason="drain timeout"))
        deadline = time.time() + 2.0
        while "not spoken" not in tab.log.toPlainText() and time.time() < deadline:
            tab._drain(); qt_app.processEvents()
        assert "not spoken — drain timeout" in tab.log.toPlainText()
        assert "audio_io" in tab.log.toPlainText()
    finally:
        tab.close()
        bus.close()


# ── the roster, as cards ─────────────────────────────────────────

def tmp_pack(*, clip: str) -> pathlib.Path:
    """A throwaway pack whose only art is something Qt cannot decode."""
    import tempfile
    root = pathlib.Path(tempfile.mkdtemp(prefix="pack-"))
    (root / clip).write_bytes(b"not really a video")
    (root / "character.yaml").write_text(
        f"name: unreadable\nrender:\n  asset: {clip}\n", encoding="utf-8")
    return root


def test_every_pack_gets_a_tile():
    """A roster where half the entries are blank rectangles is worse
    than no roster, and most packs will never have a card drawn for
    them — so the fallback reuses the art they already ship."""
    from interfaces.character_cards import card_for

    authored = card_for(ROOT / "characters/mochi")
    assert authored is not None and authored.name == "card.png"

    # Every installed pack resolves to real art now — the ones whose
    # faces are JSON data got a rendered card.png from
    # dev/tools/make_cards.py, which is the point of that tool.
    from interfaces.player import _roster
    for identifier, _label, root in _roster():
        found = card_for(root)
        assert found is not None and found.is_file(), f"{identifier} has no tile"

    # The last rung still has to hold: a pack whose art Qt cannot decode
    # is selectable by name rather than crashing or drawing nothing.
    unreadable = tmp_pack(clip="face.mp4")
    assert card_for(unreadable) is None
    assert card_for(ROOT / "characters/does-not-exist") is None


def test_the_cards_key_on_the_id_the_rest_of_the_app_uses():
    """The folder is a display convention — "Cyber Cat" is the pack
    `cat`. Keying cards on the folder name is exactly why the strip and
    the dropdown could not select each other's choices."""
    from interfaces.player import _roster

    ids = [identifier for identifier, _label, _folder in _roster()]
    assert ids == animation.available()
    assert "cat" in ids and "Cyber Cat" not in ids
    for identifier, label, folder in _roster():
        assert (folder / "character.yaml").is_file(), identifier
        assert label, identifier


def test_a_card_and_the_dropdown_cannot_disagree(monkeypatch):
    """Two ways to choose a character, one truth. Whichever moves, the
    other follows — the same rule the audio switches follow."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("MOCHI_NO_CYCLE", "1")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus
    from interfaces.player import FaceTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = SimpleNamespace(bus=InProcBus(), root=ROOT, config={})
    tab = FaceTab(app, (QtCore, QtGui, QtWidgets),
                  {"character": "mochi", "scale": 1})
    selected = lambda: [n for n, b in tab.cards._buttons.items() if b.isChecked()]
    try:
        assert selected() == ["mochi"]

        tab.cards._buttons["patric"].click()
        qt_app.processEvents()
        assert tab.pack_box.currentText() == "patric"
        assert tab.character.name == "patric"

        tab.pack_box.setCurrentText("cat")
        qt_app.processEvents()
        assert selected() == ["cat"]
    finally:
        tab.close()


def test_switching_character_re_voices_the_running_mind(monkeypatch):
    """A character is a face AND a voice. Switching one must switch
    both, and must not cost a model reload — the agent reads its system
    prompt per turn, so both halves are assignments.

    This also pins `self.app` on the Face tab: Qt swallows exceptions
    raised inside a slot, so a missing attribute here fails silently and
    the character changes its face while keeping the old voice.
    """
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("MOCHI_NO_CYCLE", "1")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus
    from interfaces.player import FaceTab

    class _Agent:
        def __init__(self) -> None:
            self.system_prompt = "the old voice"

    class _RuntimeConfig:
        system_prompt = "the old voice"

    class _Runtime:
        def __init__(self) -> None:
            self.config = _RuntimeConfig()
            self._sessions = {"mochi-1": _Agent()}

    class _MindSupervisor(_FakeSupervisor):
        def __init__(self) -> None:
            super().__init__()
            self.runtime = _Runtime()

        def node(self, node_id: str):
            return self if node_id == "mind" else super().node(node_id)

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    supervisor = _MindSupervisor()
    app = SimpleNamespace(bus=InProcBus(), root=ROOT, config={},
                          supervisor=supervisor)
    tab = FaceTab(app, (QtCore, QtGui, QtWidgets),
                  {"character": "mochi", "scale": 1})
    try:
        tab.pack_box.setCurrentText("bitmap_man")
        qt_app.processEvents()
        runtime = supervisor.runtime
        # the conversation already open
        live = runtime._sessions["mochi-1"].system_prompt
        assert "Bitmap Man" in live or "monochrome" in live, live
        # and the seed for sessions built later — "New conversation"
        assert runtime.config.system_prompt == live
        # written back to config too, so a node rebuilt later agrees
        assert app.config["mind"]["system_prompt"] == live
    finally:
        tab.close()


# ── performances are mscripts, saved with the character ──────────

def test_a_performance_is_a_saved_mscript_not_code():
    """Scenes are DATA in the character's own mscripts/, so the MScript
    Editor opens them and the node graph draws them. A performance that
    only exists as Python is one an author cannot write."""
    from core import scenes

    character = animation.load("bitmap_man")
    found = {s.name: s for s in scenes.available(character)}
    assert {"idle", "knock knock", "looking around"} <= set(found)
    for scene in found.values():
        assert scene.path.suffix == ".mscript"
        assert scene.path.parent.name == "mscripts"
        assert scene.path.parent.parent == pathlib.Path(character.root)

    # and the SAME parser the editor uses reads them
    from interfaces.mscript_editor import parse_mscript, parse_steps

    text = found["knock knock"].path.read_text(encoding="utf-8")
    commands = [s.command for s in parse_steps(parse_mscript(text)["main"])
                if s.command]
    assert commands.count("SAY") == 3
    assert commands.count("LISTEN") == 2


def test_the_three_scenes_are_progressively_harder():
    """Each demo proves one more thing than the last."""
    from core import scenes

    by_name = {s.name: s for s in scenes.available(animation.load("bitmap_man"))}
    # a loop, expressed the way the engine expresses one
    assert by_name["idle"].loop and not by_name["idle"].interactive
    # face and voice on one clock, ending on its own
    assert not by_name["looking around"].loop
    assert any(s.kind == "say" for s in by_name["looking around"].steps)
    # and the one that stops for a person
    assert by_name["knock knock"].interactive


def test_an_animation_only_script_is_not_offered_as_a_performance():
    """blink.mscript is the ENGINE's to play — all BITMAP commands, no
    face, voice or wait for anyone. Offering it as a Stage button would
    be a button that does nothing visible."""
    from core import scenes

    character = animation.load("bitmap_man")
    assert (pathlib.Path(character.root) / "mscripts/blink.mscript").is_file()
    assert "blink" not in {s.name for s in scenes.available(character)}


def test_a_toolless_model_can_still_drive_the_face():
    """The whole no-tools claim: an LLM that can only return TEXT still
    performs, because a leading marker is applied by the app and
    stripped before synthesis. Only the character's OWN vocabulary is
    accepted — a model will invent faces a pack does not have."""
    from core import expressive

    faces = list(animation.load("bitmap_man").expressions)
    assert expressive.split("[happy] Ooh, hi!", faces) == ("happy", "Ooh, hi!")
    assert expressive.split("  [LOOK_UP] Up there!", faces) == (
        "look_up", "Up there!")
    # invented face: dropped, and never read aloud either
    assert expressive.split("[excited] hello", faces) == ("", "hello")
    assert expressive.split("no marker", faces) == ("", "no marker")

    # the entire cost of performing without tools
    block = expressive.perform_block(faces)
    assert all(face in block for face in faces)
    assert len(block) < 400, "this has to stay obviously cheaper than a schema"


def test_a_scene_can_do_two_things_at_once():
    """The reason a timeline exists beside a performance script: a
    program counter says one thing at a time, so "look around WHILE you
    talk" cannot be written in one. Here the eyes move during a line."""
    from core import staging

    timeline = staging.load(ROOT / "characters/bitmap man/scenes/secret.json")
    speech = next(t for t in timeline.tracks if t.kind == "speech")
    faces = next(t for t in timeline.tracks if t.kind == "animation")

    line = speech.clips[0].t_offset_ms
    next_line = speech.clips[1].t_offset_ms
    during = [c for c in faces.clips if line < c.t_offset_ms < next_line]
    assert len(during) >= 2, "no face change happens while a line is spoken"


def test_expressions_resolve_against_the_character_at_load():
    """An author writes `expression: look_up`, not a path three
    directories down. Resolving needs the pack, so Mochi does it and the
    scheduler still receives plain asset paths — and a typo fails when
    you OPEN the scene, not three seconds into a performance."""
    import pytest
    from core import staging
    from jaeger_os.timeline import Timeline, TimelineClip, TimelineTrack

    timeline = staging.load(ROOT / "characters/bitmap man/scenes/secret.json")
    glance = next(c for c in timeline.tracks[0].clips if c.label == "glance up")
    assert glance.payload["asset"].endswith("look_up.json")
    assert pathlib.Path(glance.payload["asset"]).is_file()

    broken = Timeline(name="x", tracks=[TimelineTrack(
        kind="animation", target="bitmap_man",
        clips=[TimelineClip(t_offset_ms=0, payload={"expression": "smoulder"})])])
    with pytest.raises(staging.StagingError) as exc:
        staging.resolve(broken, ROOT)
    assert "smoulder" in str(exc.value)


def test_a_track_says_who_as_well_as_what():
    """`kind` is what a clip means, `target` is who does it. One
    character never needs it; two do, and so does a body with three
    servos."""
    from core import staging

    timeline = staging.load(ROOT / "characters/bitmap man/scenes/secret.json")
    targets = {t.kind: t.target for t in timeline.tracks}
    assert targets["animation"] == "bitmap_man"
    assert targets["light"] == "desk"      # not the character — the room


def test_a_timeline_runs_mscripts_concurrently():
    """The join: a track is the channel, a cue is that channel's
    program, and concurrency comes from having several tracks — not from
    making one sequencer multi-threaded.

    Two script tracks and a speech track share one t=0. The eyes cue
    loops the whole time the voice track is firing, which is the thing a
    single program counter cannot express.
    """
    from jaeger_os.timeline import TRACK_SCRIPT
    from core import staging

    timeline = staging.load(ROOT / "characters/bitmap man/scenes/two_cues.json")
    cues = [t for t in timeline.tracks if t.kind == TRACK_SCRIPT]
    assert len(cues) == 2, "the point is more than one cue at once"
    for track in cues:
        for clip in track.clips:
            script = ROOT / clip.payload["script"]
            assert script.is_file(), script
            # a cue is an mscript — the same files the editor opens
            assert script.suffix == ".mscript"

    # and the cue that runs alongside the voice is a LOOP, so it keeps
    # going for as long as the track needs it to
    from core import scenes

    wander = scenes.load(ROOT / "characters/bitmap man/mscripts/glance_about.mscript")
    assert wander.loop and not wander.interactive


# ── where the logic lives ────────────────────────────────────────

def test_the_rules_of_a_game_are_code():
    """Measured, not assumed: gemma-4-E4B plays 24/24 LEGAL moves and
    1/24 optimal, misses 3 of 5 forced blocks, and only ever chooses
    squares 1, 2 or 4. It is not reading the position — it has a
    positional prior. So rules and move choice are code, and the model
    does the talking, which is the part it is actually good at."""
    from nodes.tictactoe import game as ttt

    board = ttt.new_board()
    assert len(ttt.legal(board)) == 9

    # perfect play blocks a forced loss every time — this is the exact
    # case the model missed three times in five
    assert ttt.best_move("XX O     ", "O") == 2
    assert ttt.best_move("X   X    ", "O") == 8

    # and takes a win when it has one
    assert ttt.winner(ttt.place("XX       ", 2, "X")) == "X"
    assert ttt.over("XXXOO    ")
    assert ttt.threat("XX       ", "X") == "about to win"
    assert ttt.threat("OO       ", "X") == "about to lose"


def test_a_position_is_described_in_words_not_ascii_art():
    """A model reads tokens, not pictures. A pipes-and-dashes grid is
    a picture; naming the squares is what it can actually use — and the
    numbering is stated so a reply parses back."""
    from nodes.tictactoe import game as ttt

    described = ttt.describe(ttt.place(ttt.new_board(), 4, "X"))
    assert "centre (4) is X" in described
    assert "Free squares:" in described
    assert "|" not in described          # that is render(), for humans
    assert "|" in ttt.render(ttt.new_board())


def test_perfect_play_never_loses():
    """The property that makes it a worthy opponent, checked by playing
    it against every legal reply rather than trusting the algorithm."""
    from nodes.tictactoe import game as ttt

    def explore(board: str, turn: str) -> None:
        if ttt.over(board):
            assert ttt.winner(board) != "O", f"minimax lost: {board!r}"
            return
        if turn == "X":
            explore(ttt.place(board, ttt.best_move(board, "X"), "X"), "O")
            return
        for square in ttt.legal(board):
            explore(ttt.place(board, square, "O"), "X")

    explore(ttt.new_board(), "X")


def test_rules_over_a_policy_remove_losses_the_policy_makes():
    """The hybrid thesis, checked: a learned preference under hard
    constraints. The policy alone loses games; the same weights under
    two rules do not."""
    from nodes.tictactoe import (HybridPlayer, HeuristicPlayer, MinimaxPlayer,
                                 NeuralPlayer, RandomPlayer, duel)

    net = NeuralPlayer(hidden=32).train(positions=30_000)
    rivals = (RandomPlayer(seed=1), HeuristicPlayer(), MinimaxPlayer())
    lost = lambda p: sum(duel(p, r, games=30, seed=4)[r.name] for r in rivals)
    assert lost(HybridPlayer(policy=net, intent="win")) == 0


def test_known_rules_make_evolution_far_cheaper():
    """Measured: bare evolution reaches ~23% agreement and loses half
    its games; the SAME budget spent evolving inside the rules reaches
    ~52% and loses none. Encoding what is already known shrinks the
    space the search has to cover — you do not pay to rediscover the
    rules."""
    from nodes.tictactoe import HybridPlayer, RandomPlayer, duel, evolve

    bred = evolve(population=16, generations=25, games=8, seed=2,
                  with_rules=True)
    guarded = HybridPlayer(policy=bred, intent="win")
    assert duel(guarded, RandomPlayer(seed=1), games=30, seed=4)["random"] == 0


def test_a_character_chooses_how_hard_to_play():
    """Absolute knowledge of the rules, personality about how to use it.
    A softened move is CHOSEN by value, not randomised — a random bad
    move reads as a bug, the second-best reads as going easy on you."""
    from nodes.tictactoe import (HybridPlayer, NeuralPlayer, RandomPlayer,
                                 duel, game)

    net = NeuralPlayer(hidden=32).train(positions=30_000)
    kid = RandomPlayer(seed=3)
    hard = duel(HybridPlayer(policy=net, intent="win"), kid, games=40, seed=4)
    easy = duel(HybridPlayer(policy=net, intent="let"), kid, games=40, seed=4)
    assert hard["random"] == 0, "playing to win should not lose to random"
    assert easy["random"] > hard["random"], "conceding should let them win"

    # every move is still legal and understood — softening is not flailing
    board = game.new_board()
    player = HybridPlayer(policy=net, intent="let")
    assert player.move(board, "X") in game.legal(board)
    assert dict(game.rank(board, "X"))[player.move(board, "X")] is not None


def test_any_agent_can_play_a_game():
    """A Session is the surface a character plays through: it knows
    turns and outcomes and nothing about faces, buses or models. Give it
    a strategy and the turn-taking is identical whichever one it is."""
    from nodes.tictactoe import STRATEGIES, Session

    for name in ("random", "heuristic", "minimax", "hybrid"):
        session = Session(strategy=name, trained=2_000)
        while not session.over:
            assert session.agent_turn() is not None or session.over
            if session.over:
                break
            session.human_turn(session.legal()[0])
        assert session.result in ("agent", "human", "draw")
        assert session.situation() in ("you won", "you lost", "it is a draw")

    # an illegal move is refused, not silently corrected
    session = Session(strategy="minimax")
    session.agent_turn()
    taken = [i for i in range(9) if session.board[i] != " "][0]
    assert session.human_turn(taken) is None
    assert session.human_turn(99) is None


def test_a_move_carries_what_a_character_needs_to_react():
    """The state comes back as a WORD, not a score — a model asked to be
    dramatic about "-7" writes nonsense. And the face is derivable
    immediately, because a reaction that waits for inference is not a
    reaction."""
    from nodes.tictactoe import FACE_FOR, Session

    session = Session(strategy="minimax")
    move = session.agent_turn()
    assert move.state in FACE_FOR
    assert move.face == FACE_FOR[move.state]
    assert move.by == "minimax"
    assert move.board.count("X") == 1

    # the state is always from the AGENT's point of view, so a character
    # says the right thing about its opponent's move too
    session = Session(strategy="minimax")
    session.board = "OO       "
    assert session.human_turn(2) is not None
    assert session.situation() == "you lost"


def test_either_seat_takes_a_strategy_or_a_person():
    """The same object covers a character playing you and two
    strategies playing each other — so 'any agent can partake' means
    either side, not just one."""
    from nodes.tictactoe import Session

    versus = Session(strategy="minimax", opponent="heuristic", trained=2_000)
    assert versus.autonomous
    moves = versus.play_out()
    assert versus.over and versus.result in ("agent", "human", "draw")
    assert {m.by for m in moves} == {"minimax", "heuristic"}

    # a human seat refuses to be played out — silently skipping someone's
    # turn is a game they never got to play
    import pytest

    solo = Session(strategy="minimax")
    assert not solo.autonomous
    with pytest.raises(ValueError):
        solo.play_out()

    # step() is the one call both shapes use
    assert solo.step() is not None          # the agent moves
    assert solo.step() is None              # then it is your turn
    assert solo.human_turn(solo.legal()[0]) is not None

    # and a strategy's seat cannot be played by hand
    taken = Session(strategy="minimax", opponent="random", trained=2_000)
    taken.step()
    assert taken.human_turn(taken.legal()[0]) is None


def test_a_speech_track_gets_the_characters_own_voice():
    """A track's `target` is a CHARACTER id; a synthesiser wants a VOICE
    id, and only the pack knows which. Filling the voice with the target
    was a bug — it sent "jaeger" to a synthesiser expecting "bm_george"."""
    from core import staging

    timeline = staging.load(
        ROOT / "characters/Jaeger/scenes/hello_fellow_humans.json")
    speech = next(t for t in timeline.tracks if t.kind == "speech")
    assert speech.target == "jaeger"
    voices = {c.payload["voice"] for c in speech.clips}
    # the pack's own voice, plus the one the scene deliberately overrides
    assert "bm_george" in voices and "gm_fritz" in voices
    assert "jaeger" not in voices

    # a clip that names its own voice keeps it — that is a performance
    # decision, not a lookup
    slip = next(c for c in speech.clips if c.label == "the mask slips")
    assert slip.payload["voice"] == "gm_fritz"


def test_the_introduction_opens_on_the_line():
    """The scene is the demo; the line is the point of it."""
    from core import staging

    timeline = staging.load(
        ROOT / "characters/Jaeger/scenes/hello_fellow_humans.json")
    speech = next(t for t in timeline.tracks if t.kind == "speech")
    first = min(speech.clips, key=lambda c: c.t_offset_ms)
    assert first.payload["text"] == "Hello, fellow humans."
    # and the mood track flips cold exactly when the mask slips
    lights = next(t for t in timeline.tracks if t.kind == "light")
    slip = next(c for c in speech.clips if c.label == "the mask slips")
    assert any(c.t_offset_ms == slip.t_offset_ms for c in lights.clips)


def test_a_scene_lives_with_the_character_it_needs():
    """A timeline is not an asset — it references assets the way a score
    references instruments. And it names one character's expressions, so
    it will not play without that pack: it belongs in the pack, beside
    the mscripts it performs."""
    from core import staging

    for name, expected in (("bitmap_man", {"secret", "two cues"}),
                           ("jaeger", {"hello fellow humans"}),
                           ("mochi", {"greeting"})):
        character = animation.load(name)
        found = {label for label, _path in staging.available(character)}
        assert expected <= found, name
        for label, path in staging.available(character):
            assert path.parent.name == "scenes"
            if "(shared)" in label:
                # a two-hander belongs to neither character and lives at
                # the project root — offered to both, owned by neither
                assert path.parent.parent == ROOT
            else:
                assert path.parent.parent == pathlib.Path(character.root)

    # a pack with no scenes of its own still sees the shared ones
    solo = [label for label, _p in staging.available(animation.load("cat"))]
    assert all("(shared)" in label for label in solo)
    # and nothing is left in assets/
    assert not (ROOT / "assets/timelines").exists()


def test_every_scene_resolves_against_its_own_pack():
    """The test that catches a scene filed under the wrong character:
    every expression it names has to exist in the pack it sits in."""
    from core import staging

    for character_dir in sorted((ROOT / "characters").iterdir()):
        for scene in sorted((character_dir / "scenes").glob("*.json")):
            timeline = staging.load(scene)      # raises StagingError if not
            for track in timeline.tracks:
                for clip in track.clips:
                    asset = (clip.payload or {}).get("asset")
                    if asset:
                        assert pathlib.Path(asset).is_file(), (scene, asset)


def test_one_mscript_can_hold_both_shapes():
    """FANUC's split: the listing is the source, the compiled form is
    what runs. `[Main]` is the sequential program; `[Track_*]` sections
    are channels on a clock. They were never rigidly different — the
    section mechanism has accepted arbitrary names since Mochi 3.0 and
    was simply unused."""
    from core import scenes
    from interfaces.mscript_editor import parse_mscript

    path = ROOT / "characters/bitmap man/mscripts/secret.mscript"
    assert scenes.has_tracks(path)

    timeline = scenes.compile_timeline(path, target="bitmap_man")
    assert {t.kind for t in timeline.tracks} == {"animation", "speech", "light"}
    assert {t.name for t in timeline.tracks} == {"eyes", "voice", "light"}
    assert timeline.computed_duration_ms() == 8200

    # T[seconds] is absolute — a track says WHEN, not what-comes-next
    voice = next(t for t in timeline.tracks if t.kind == "speech")
    assert [c.t_offset_ms for c in voice.clips] == [600, 3000, 5400]

    # and the eyes move DURING a line, which is the whole point
    eyes = next(t for t in timeline.tracks if t.kind == "animation")
    during = [c for c in eyes.clips if 600 < c.t_offset_ms < 3000]
    assert len(during) >= 2

    # a plain performance has no tracks and belongs to the runner
    plain = ROOT / "characters/bitmap man/mscripts/knock_knock.mscript"
    assert not scenes.has_tracks(plain)
    assert scenes.compile_timeline(plain) is None

    # the section mechanism itself needed no change
    sections = parse_mscript(path.read_text(encoding="utf-8"))
    assert {"track_eyes", "track_voice", "track_light"} <= set(sections)


def test_a_compiled_scene_resolves_like_an_authored_one():
    """Whichever form it was written in, the pack fills in the same
    things — expressions become assets, the character's voice fills in."""
    from core import scenes, staging

    timeline = scenes.compile_timeline(
        ROOT / "characters/bitmap man/mscripts/secret.mscript",
        target="bitmap_man")
    staging.resolve(timeline, ROOT)
    eyes = next(t for t in timeline.tracks if t.kind == "animation")
    assert eyes.clips[1].payload["asset"].endswith("look_up.json")
    voice = next(t for t in timeline.tracks if t.kind == "speech")
    assert voice.clips[0].payload["voice"] == "gm_fritz"   # bitmap man's own


def test_a_show_file_runs_channels_and_a_program_at_once():
    """The animatronic shape. A figure moves, speaks and reacts on the
    same beat, so a show file is not a sequence OR a timeline — it is
    both, from one file, starting at the same t=0.

    A clock cannot wait for a person; a program counter cannot overlap.
    Neither alone is a show."""
    from core import scenes

    path = ROOT / "characters/bitmap man/mscripts/show.mscript"

    channels = scenes.compile_timeline(path, target="bitmap_man")
    assert {t.kind for t in channels.tracks} == {
        "animation", "speech", "light", "motion"}

    # motion has no node yet and still keeps time — authoring ahead of
    # the hardware is the normal case for an animatronic
    motion = next(t for t in channels.tracks if t.kind == "motion")
    assert [c.payload["joint"] for c in motion.clips][:2] == [
        "neck_pan", "neck_pan"]
    assert motion.clips[0].t_offset_ms == 1200

    # and the same file carries the part a clock cannot express
    program = scenes.load(path)
    assert program.interactive
    assert [s.kind for s in program.steps] == [
        "wait", "say", "listen", "face", "ask", "face"]


def test_an_unknown_channel_still_keeps_time():
    """A track kind with no consumer is scheduled and not dispatched, so
    a scene authored for hardware nobody has yet plays correctly on the
    channels that do exist."""
    from core import scenes

    timeline = scenes.compile_timeline(
        ROOT / "characters/bitmap man/mscripts/show.mscript",
        target="bitmap_man")
    assert timeline.computed_duration_ms() >= 6600


def test_the_section_vocabulary_is_declared_not_open():
    """MochiScript has had a fixed set of sections since v2.0 and that
    rigidity is deliberate. A permissive parser is not a feature: it
    diverged from the engine, so a file could look fine in the editor
    and lose whole blocks when played."""
    from interfaces.mscript_editor import (KNOWN_SECTIONS, parse_mscript,
                                           unknown_sections)
    import pytest

    assert KNOWN_SECTIONS == ("Header", "Resources", "Main", "Keyframes")

    valid = ("[Main start]\nWAIT D[1]\n[Main end]\n"
             "[Track_eyes start]\nFACE EXPR[a] T[0]\n[Track_eyes end]\n")
    assert {"main", "track_eyes"} <= set(parse_mscript(valid, strict=True))
    assert unknown_sections(valid) == []

    typo = "[Maim start]\nWAIT D[1]\n[Maim end]\n"
    with pytest.raises(ValueError):
        parse_mscript(typo, strict=True)
    # but the editor can still OPEN it, because refusing to display a
    # typo is how a typo becomes unrecoverable
    assert parse_mscript(typo) is not None
    assert unknown_sections(typo) == ["[Maim start]", "[Maim end]"]


def test_both_readers_agree_on_the_vocabulary():
    """The bug this closes: Mochi's editor accepted any section name
    while the engine accepted three, so a show file was valid here and
    lost every track there."""
    from jaeger_animation.procedural.mscript_engine import KNOWN_SECTIONS as ENGINE
    from interfaces.mscript_editor import KNOWN_SECTIONS as EDITOR

    assert set(EDITOR) == set(ENGINE)


def test_the_engine_accepts_a_show_file_without_losing_it(tmp_path):
    """A file with tracks has to be VALID to the engine even though the
    engine does not schedule them — otherwise the same document means
    two different things depending on who opened it."""
    from jaeger_animation.procedural.mscript_engine import MscriptScript

    show = tmp_path / "show.mscript"
    show.write_text(
        "[Main start]\nWAIT D[1.0]\n[Main end]\n"
        "[Track_voice start]\nSAY TXT['hi'] T[0.4]\n[Track_voice end]\n")
    script = MscriptScript(str(show))          # must not raise
    assert script._instructions                # [Main] survived

    broken = tmp_path / "broken.mscript"
    broken.write_text("[Mian start]\nWAIT D[1]\n[Mian end]\n")
    import pytest
    with pytest.raises(ValueError):
        MscriptScript(str(broken))


# ── two characters, one scene ────────────────────────────────────

def test_the_twins_are_a_matched_pair():
    """Eric and Deborahbot share a vocabulary so a two-hander can
    address either with the same commands, and differ in the only
    things a scene should have to care about: voice and manner."""
    import yaml

    eric, deb = animation.load("eric"), animation.load("deborahbot")
    assert list(eric.expressions) == list(deb.expressions)
    assert eric.kind == deb.kind == "clip_set"

    sheets = {name: yaml.safe_load(
        (pathlib.Path(animation.load(name).root) / "character.yaml")
        .read_text(encoding="utf-8"))
        for name in ("eric", "deborahbot")}
    voices = {s["identity"]["voice_id"] for s in sheets.values()}
    assert len(voices) == 2, "twins that sound the same are one character"
    for sheet in sheets.values():
        assert sheet["prompt"]["custom_instructions"]


def test_a_track_name_carries_who_as_well_as_what():
    """`Track_<target>_<channel>`. Matching the whole suffix was the bug:
    `Track_eric_voice` fell through to animation, so a two-hander's
    dialogue was silently scheduled on the wrong channel."""
    from core import scenes

    assert scenes.track_parts("track_eric_voice") == ("eric", "speech", "eric_voice")
    assert scenes.track_parts("track_deborahbot_face") == (
        "deborahbot", "animation", "deborahbot_face")
    # a solo names no target — the app supplies one
    assert scenes.track_parts("track_voice") == ("", "speech", "voice")
    assert scenes.track_parts("track_light") == ("", "light", "light")


def test_a_two_hander_lives_at_the_project_root():
    """It belongs to NEITHER character, which is the whole reason a
    track carries a target."""
    from core import scenes, staging

    path = ROOT / "scenes/hello_fellow_humans.mscript"
    assert path.is_file()

    timeline = scenes.compile_timeline(path)
    staging.resolve(timeline, ROOT)
    by_target = {}
    for track in timeline.tracks:
        by_target.setdefault(track.target, set()).add(track.kind)
    assert by_target["eric"] == {"animation", "speech"}
    assert by_target["deborahbot"] == {"animation", "speech"}

    # each speaks in its OWN voice, resolved from its own pack
    voices = {t.target: t.clips[0].payload["voice"]
              for t in timeline.tracks if t.kind == "speech"}
    assert voices["eric"] != voices["deborahbot"]

    # and each shows its OWN faces
    faces = {t.target: t.clips[1].payload["asset"]
             for t in timeline.tracks if t.kind == "animation"}
    assert "Eric/" in faces["eric"]
    assert "Deborahbot 5000/" in faces["deborahbot"]
    for asset in faces.values():
        assert pathlib.Path(asset).is_file()

    # the shared directory is discoverable from any character
    labels = {name for name, _p in staging.available(animation.load("eric"))}
    assert any("shared" in label for label in labels)


def test_a_scene_loads_whichever_form_it_was_written_in():
    """`.mscript` is the authoring form and compiles; `.json` is the
    compiled form and loads. A caller picking from a list should not
    have to know which — handing an mscript to the JSON decoder is what
    produced `Expected 'object', got 'array'` the moment shared scenes
    started being offered."""
    from core import staging

    listing = staging.load(ROOT / "scenes/hello_fellow_humans.mscript")
    assert len(listing.tracks) == 5
    compiled = staging.load(ROOT / "characters/bitmap man/scenes/secret.json")
    assert compiled.tracks

    # every scene the Stage offers must actually open
    for name in ("bitmap_man", "jaeger", "mochi", "eric"):
        for label, path in staging.available(animation.load(name)):
            staging.load(path)          # raises if it cannot


def test_only_the_visible_tab_drives_the_display(monkeypatch):
    """The Face tab walks its character's expressions on a timer; the
    Stage drives a performance. Both publish to /act/display/play, so
    with both live the screen alternates between two characters'
    artwork. A background tab has no business driving the display."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from jaeger_os import InProcBus
    from interfaces.window import MochiWindow

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = SimpleNamespace(
        bus=InProcBus(), config={"player": {"character": "emotes", "scale": 1}},
        spec=SimpleNamespace(nodes=[]), supervisor=None, root=ROOT)
    window = MochiWindow(app)
    try:
        tabs = [window.widget.tabText(i) for i in range(window.widget.count())]
        window.widget.setCurrentIndex(0)
        window.face.cycle_btn.setChecked(True)
        assert window.face.cycle_btn.isChecked()

        window.widget.setCurrentIndex(tabs.index("Stage"))
        assert not window.face.cycle_btn.isChecked(), \
            "the Face tab kept driving the display from the background"

        window.widget.setCurrentIndex(0)
        assert window.face.cycle_btn.isChecked(), "cycling was not restored"
    finally:
        window.close()


def test_the_jaeger_ai_avatar_surfaces_are_offered_for_review():
    """Under review, not integrated. JaegerAI is a sibling product, not
    a Mochi module — the launcher puts its source on the path rather
    than installing it, so looking at a design costs nothing and commits
    to nothing."""
    from interfaces.legacy_windows import legacy_window_specs

    specs = {s.id: s for s in legacy_window_specs(ROOT)
             if s.generation == "JaegerAI"}
    assert {"jai-orb", "jai-player", "jai-avatar", "jai-chat"} <= set(specs)
    for spec in specs.values():
        assert spec.source.is_file()
        assert spec.source.name == "jaeger_ai_windows.py"
        assert "review" in spec.note

    # the launcher knows the same set, so a row cannot point at nothing
    from dev.tools.jaeger_ai_windows import WINDOWS

    assert {s.command[-1] for s in specs.values()} == set(WINDOWS)


def test_the_manual_node_strip_switches_a_node_and_reads_it_back(monkeypatch):
    """Mochi 3.0's panel had Turn On / Turn Off per node and v5 lost it.

    The point of the rebuild is that the button does not remember its own
    click: it starts a node through the supervisor and then reports what
    the supervisor says, so a node that fails to start reads "stopped".
    """
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus
    from interfaces.runtime import RuntimeTab

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = InProcBus()
    supervisor = _FakeSupervisor(declared=("audio_io", "vision", "mind"))
    app = SimpleNamespace(bus=bus, supervisor=supervisor, config={})
    tab = RuntimeTab(app, (QtCore, QtGui, QtWidgets))
    try:
        # Every declared node gets a row, including ones no tab owns.
        assert set(tab._rows) == {"audio_io", "vision", "mind"}
        tab._refresh_nodes()
        assert tab._rows["mind"]["toggle"].text() == "Turn on"

        tab._toggle("mind")
        deadline = time.time() + 2.0
        while not tab._switches and time.time() < deadline:
            time.sleep(0.01)
        tab._refresh_nodes()
        assert "mind" in supervisor.running, "the button did not start the node"
        assert tab._rows["mind"]["state"].text() == "running"
        assert tab._rows["mind"]["toggle"].text() == "Turn off"

        # And back off, with the label following the supervisor again.
        tab._toggle("mind")
        deadline = time.time() + 2.0
        while not tab._switches and time.time() < deadline:
            time.sleep(0.01)
        tab._refresh_nodes()
        assert "mind" not in supervisor.running
        assert tab._rows["mind"]["toggle"].text() == "Turn on"
    finally:
        tab.close(); bus.close()


def test_the_avatar_window_is_a_character_with_a_panel_that_pulls_out(monkeypatch):
    """The agent's primary window: the character alone until you ask for
    more, then a panel of ways to interact with it.

    Panes are lazy on purpose — a chat nobody opened must not be
    subscribed to anything — so this checks the window starts with none
    built, and that both the chat and the game are real objects on the
    same bus once selected.
    """
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtGui, QtWidgets
    from jaeger_os import InProcBus, topics
    from interfaces.avatar_window import AvatarWindow
    from interfaces.character_view import CharacterView
    from interfaces.chat import ChatTab

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    bus = InProcBus()
    app = SimpleNamespace(bus=bus, supervisor=_FakeSupervisor(), config={})
    view = CharacterView(app)
    window = AvatarWindow(app)
    try:
        view.show(); window.show()

        # Closed, and nothing built. The character is the whole window.
        assert not window.panel.isVisible()
        assert window._built == {}
        assert window.handle.text() == "\u203a"

        # One publish, two independent subscribers, no forwarding.
        bus.publish(topics.DisplayFrame(
            width=8, height=8, data=bytes([90, 160, 220, 255] * 64)))
        deadline = time.time() + 2.0
        while view._frame is None and time.time() < deadline:
            qt_app.processEvents(); time.sleep(0.01)
        view._repaint(); window.view._repaint()
        assert not view.screen.pixmap().isNull()
        assert not window.view.screen.pixmap().isNull()

        # Pulling the panel out builds the first pane and widens the
        # window rather than squeezing the character.
        narrow = window.width()
        window.toggle_panel()
        qt_app.processEvents()
        assert window.panel.isVisible()
        assert window.width() > narrow
        assert window.handle.text() == "\u2039"

        # The chat pane is the REAL tab, with the switches that move
        # nodes — not a re-drawn one that can only write settings.
        chat = window._built["chat"]
        assert isinstance(chat, ChatTab)
        assert chat.bus is bus
        assert hasattr(chat, "mic") and hasattr(chat, "speak")

        # A second pane, which is what makes the panel a panel. It is
        # built only when picked, and it plays a real game.
        assert "game" not in window._built
        game = window.show_pane("game")
        assert window.stack.currentWidget() is game.widget
        game.start()
        assert game.game is not None
        assert sum(c != " " for c in game.game.board) == 1, "it did not open"

        # And it folds back to just the character.
        window.toggle_panel()
        assert not window.panel.isVisible()
        assert window.width() == narrow
    finally:
        window.shutdown(); view.shutdown(); bus.close()


def test_picking_a_cast_card_switches_the_character_everywhere(monkeypatch):
    """The Cast tab is a VIEW of who the agent is, not a second owner.

    A card click routes through the Face tab's pack box — the one code
    path that loads a character — so the display, the persona and the
    voice move together, and the avatar window follows without the Cast
    tab knowing that window exists. That last part is the requirement,
    and it is what this checks.
    """
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from jaeger_os import JaegerApp
    from interfaces.window import MochiWindow

    qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = JaegerApp(ROOT / "sim.toml")
    app.boot()
    window = MochiWindow(app)
    try:
        window.start()
        manager = window.window_manager
        manager.show_avatar()

        def settle(seconds: float = 1.2) -> None:
            deadline = time.time() + seconds
            while time.time() < deadline:
                qt_app.processEvents(); time.sleep(0.02)

        settle()
        assert window.cast.cards, "no cards were built"
        # Exactly one card is marked, and it is the live character.
        marked = [n for n, c in window.cast.cards.items() if c._active]
        assert marked == [window.face.character.name]

        # Every card offers EDIT, and none of them do anything yet —
        # a button that lies is worse than one that says it is not ready.
        assert all(not c.edit.isEnabled() for c in window.cast.cards.values())

        other = next(n for n in window.cast.cards if n != marked[0])
        before = manager.avatar.view._frame
        before = before.copy() if before is not None else None

        window.cast.cards[other].select.click()
        settle(2.0)

        assert window.face.character.name == other, "the pack did not switch"
        assert [n for n, c in window.cast.cards.items() if c._active] == [other]
        # The avatar window is watching the same display topic, so it
        # moved too — and its scaling now asks the NEW pack.
        assert manager.avatar.view.character_of().name == other
        assert manager.avatar.view._frame is not None
        assert before is None or manager.avatar.view._frame != before
    finally:
        window.close(); app.shutdown()
