from __future__ import annotations

import json

from core.companion_services import (
    PlayerSettingsStore,
    RecentStore,
    UnsupportedAnimation,
    color_command,
    command_for_catalog_entry,
    command_for_slot_value,
    filter_catalog_entries,
    framing_command,
    load_catalog,
    mode_off_command,
    mode_on_command,
    size_command,
)


def test_catalog_entry_command_resolution():
    gif = {
        "name": "Happy Blink",
        "type": "gifs",
        "path": "assets/gifs/happy.gif",
    }
    resolved = command_for_catalog_entry(gif)
    assert resolved.command == "node animation mode on happy"
    assert resolved.recent_name == "happy"

    script = {
        "name": "Demo",
        "type": "mscripts",
        "path": "assets/mscripts/demo.mscript",
    }
    resolved = command_for_catalog_entry(script)
    assert resolved.command == "play assets/mscripts/demo.mscript"
    assert resolved.recent_name == "demo"

    unsupported = command_for_catalog_entry({
        "name": "look_up",
        "type": "animations",
        "path": "assets/animations/look_up.json",
    })
    assert isinstance(unsupported, UnsupportedAnimation)
    assert "no runtime handler" in unsupported.message


def test_slot_value_command_resolution():
    assert command_for_slot_value("assets/gifs/wave.gif").command == (
        "node animation mode on wave"
    )
    assert command_for_slot_value({"file": "assets/math/idle.py"}).recent_name == "idle"
    assert command_for_slot_value(["assets/gifs/happy.gif"]).recent_name == "happy"
    assert command_for_slot_value([]) is None


def test_recent_store_pushes_unique_items(tmp_path):
    store = RecentStore(tmp_path / "recent.json", max_items=3)
    assert store.push("happy") == ["happy"]
    assert store.push("sad") == ["sad", "happy"]
    assert store.push("happy") == ["happy", "sad"]
    assert store.push("idle") == ["idle", "happy", "sad"]
    assert store.push("wave") == ["wave", "idle", "happy"]
    assert json.loads((tmp_path / "recent.json").read_text()) == [
        "wave",
        "idle",
        "happy",
    ]


def test_player_settings_store_normalizes_and_preserves_defaults(tmp_path):
    path = tmp_path / "player_settings.json"
    path.write_text(json.dumps({
        "canvas_w": "128",
        "canvas_h": "bad",
        "opacity": "0.5",
        "topmost": 0,
        "default_framing": "fill",
    }))
    settings = PlayerSettingsStore(path).load()
    assert settings["canvas_w"] == 128
    assert settings["canvas_h"] == 512
    assert settings["opacity"] == 0.5
    assert settings["topmost"] is False
    assert settings["default_framing"] == "fill"


def test_catalog_and_command_helpers(tmp_path):
    missing = tmp_path / "missing.json"
    assert load_catalog(missing) == {"entries": []}
    assert mode_on_command("rainbow") == "node animation mode on rainbow"
    assert mode_off_command() == "node animation mode off"
    assert size_command(64, 32) == "node animation size 64x32"
    assert framing_command("FILL") == "node animation framing fill"
    assert color_command((1, 2, 3)) == "node animation color 1 2 3"
    assert color_command((1, 2, 3), target="solid_color") == (
        "node animation color solid_color 1 2 3"
    )


def test_catalog_filtering_is_toolkit_neutral():
    entries = [
        {
            "name": "Happy Blink",
            "type": "gifs",
            "mood": "happy",
            "tags": ["face"],
            "hint": "smile",
            "author": "jon",
        },
        {
            "name": "Sad Blink",
            "type": "gifs",
            "mood": "sad",
            "tags": ["face"],
            "hint": "frown",
        },
        {
            "name": "Rainbow",
            "type": "math",
            "mood": "energetic",
            "tags": ["color"],
            "hint": "procedural",
        },
    ]

    assert [e["name"] for e in filter_catalog_entries(entries, mood="sad")] == [
        "Sad Blink"
    ]
    assert [e["name"] for e in filter_catalog_entries(entries, type_="math")] == [
        "Rainbow"
    ]
    assert [
        e["name"] for e in filter_catalog_entries(entries, curation="curated")
    ] == ["Happy Blink"]
    assert [
        e["name"] for e in filter_catalog_entries(entries, search_text="color")
    ] == ["Rainbow"]
