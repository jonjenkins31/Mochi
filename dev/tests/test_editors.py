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

    def __init__(self) -> None:
        self.running: set[str] = set()
        self.session = _FakeSession()

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
            assert sections.get("main"), script
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
            "Face", "Characters", "MScript Editor", "Modules",
            "Runtime", "Windows", "Chat", "Voice", "Hearing", "Vision",
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
    assert {spec.generation for spec in specs} <= {"Mochi 3.0", "Mochi v4"}


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
        main = parse_mscript(path.read_text())["main"]
        assert build_steps(parse_steps(main)) == "\n".join(main), \
            f"{path.name} changed just by being looked at"


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
