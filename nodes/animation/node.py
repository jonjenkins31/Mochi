# plugins/animation_node/node.py

"""
The entry point for the Mochi Animation Node plugin.

This script initializes the node, loads its configuration, and runs the main
loop that renders animations and processes commands received via ZMQ.
"""

import logging
import json
import yaml
import os
from typing import Sequence
import numpy as np
import zmq

# Since this script is in a subdirectory, we need to add the plugin's root to the Python path
# to ensure that imports like 'from animations import ...' work correctly.
import sys
from pathlib import Path

PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_ROOT not in sys.path:
    sys.path.append(PLUGIN_ROOT)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.append(PROJECT_ROOT_STR)

from animations import create_animation
from plugin_core.mochi_animations import Animation, Command
from plugin_core.logging_utils import setup_logger
from plugin_core.mscript_engine import MscriptScript
from transport.node_base import MochiNodeBase
from transport import zmq_manager
from transport.messages import Msg

# Mochi-NEXT: LLM-driven animation selection.  Parses <play name="X"/>
# / <mode name="X"/> / <stop/> tags out of LLM replies and routes them
# through the existing _process_node_command path so an LLM command
# behaves identically to a manual CLI/GUI command.
from nodes.animation.llm_command_parser import (
    AnimationCommand as _LLMAnimationCommand,
    parse as _parse_llm_commands,
)

def _merge_dicts(base: dict, overlay: dict) -> dict:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged

class AnimationNode(MochiNodeBase):
    """Manages the state and logic for rendering animations."""

    def __init__(self, node_id: str, config: dict, project_root: str, optional_topics: Sequence[bytes] | None = None):
        super().__init__(node_id, config, project_root, optional_topics)

        size_cfg = config.get("logical_size") or {}
        self.w = size_cfg.get("width", config.get("logical_width", 64))
        self.h = size_cfg.get("height", config.get("logical_height", 64))
        self.default_script = config.get("default_script")
        self.capabilities = config.get("capabilities", {})

        self.anim: Animation | None = None
        self.current_mode: str | None = None
        self.current_mode_name: str | None = None
        self.keyframes: dict[int, Animation] = {}
        self.script: MscriptScript | None = None
        self._solid_color_rgb: tuple[int, int, int] = (173, 216, 230)

        self._install_fallback(source="system", emit_event=True)
        self._load_default_script()

        self._command_handlers = {
            "mode": self._handle_mode_command,
            "size": self._handle_size_command,
            "color": self._handle_color_command,
            "play": self._handle_play_command,
            "stop": self._handle_stop_command,
        }

        # ── Mochi-NEXT: LLM bus subscription ──────────────────────
        # Set up a SUB socket draining llm.reply / ext.llm.reply
        # messages every _update_tick.  The animation node then
        # parses the reply text for <play>/<mode>/<stop> tags and
        # routes each parsed command through the existing
        # _process_node_command path so they behave identically to
        # manual ctrl-socket commands.

        # subscribe_topics may be a list of strings; coerce to bytes.
        sub_topics_raw = config.get("subscribe_topics") or []
        self._subscribe_topics: tuple[bytes, ...] = tuple(
            (s.encode("utf-8") if isinstance(s, str) else s)
            for s in sub_topics_raw
            if s
        )
        bus_sub_address = (
            config.get("bus_sub_address")
            or config.get("sub_address")
            or self.pub_addr
        )
        self._sub_socket: zmq.Socket | None = None
        if self._subscribe_topics:
            try:
                self._sub_socket = self._ctx.socket(zmq.SUB)
                self._sub_socket.setsockopt(zmq.LINGER, 0)
                for topic in self._subscribe_topics:
                    self._sub_socket.setsockopt(zmq.SUBSCRIBE, topic)
                self._sub_socket.connect(bus_sub_address)
                self.logger.info(
                    "LLM bus subscription up — topics=%s addr=%s",
                    [t.decode("utf-8", errors="ignore")
                     for t in self._subscribe_topics],
                    bus_sub_address,
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.error(
                    "Failed to set up SUB socket — LLM-driven "
                    "animation disabled: %s", exc,
                )
                self._sub_socket = None

        # Optional catalog lookup for name → asset path resolution.
        # Built by tools/build_catalog.py; falls back to mode-name
        # resolution when absent or when a name isn't in the catalog.
        self._catalog_index: dict[str, dict] = {}
        catalog_rel = config.get("catalog_path")
        if catalog_rel:
            catalog_abs = Path(project_root) / catalog_rel
            if catalog_abs.is_file():
                try:
                    raw = json.loads(catalog_abs.read_text())
                    for entry in raw.get("entries", []):
                        name = entry.get("name")
                        if name:
                            self._catalog_index[name] = entry
                    self.logger.info(
                        "Loaded catalog — %d entries",
                        len(self._catalog_index),
                    )
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning(
                        "Catalog load failed (%s) — continuing "
                        "without name lookup", exc,
                    )

    # ------------------------------------------------------------------
    # MochiNodeBase Implementation
    # ------------------------------------------------------------------

    def get_health_details(self) -> dict:
        return {
            "logical_size": {"width": self.w, "height": self.h},
            "mode": self.current_mode or "?",
        }

    def get_meta_details(self) -> dict:
        return {
            "logical_size": {"width": self.w, "height": self.h},
            "capabilities": self.capabilities,
        }

    # ------------------------------------------------------------------
    # Helpers
    def _install_fallback(self, *, source: str = "system", emit_event: bool = False):
        fallback = SolidColorAnimation(self.w, self.h, color=self._solid_color_rgb)
        if emit_event:
            self._set_animation(
                fallback,
                base_name="solid_color",
                label="solid_color",
                source=source,
                event_type="mode.changed",
                extra={"reason": "fallback"},
            )
        else:
            self.anim = fallback
            self.current_mode = "solid_color"
            self.current_mode_name = "solid_color"
        self.logger.info(f"Defaulting to solid color {self._solid_color_rgb}")

    def _set_animation(
        self,
        animation: Animation,
        *,
        base_name: str,
        label: str,
        source: str,
        event_type: str = "mode.changed",
        extra: dict | None = None,
    ) -> None:
        self.anim = animation
        self.current_mode_name = base_name
        self.current_mode = label
        if isinstance(animation, SolidColorAnimation):
            self._solid_color_rgb = tuple(int(c) for c in animation.color)
        if event_type:
            payload = {"mode": label, "base": base_name, "source": source}
            if extra:
                payload.update(extra)
            self.enqueue_event(event_type, **payload)

    def activate_mode(self, name: str, *, source: str = "ctrl", label: str | None = None) -> bool:
        name = (name or "").strip()
        if not name:
            self.enqueue_event("mode.error", message="No mode specified", source=source)
            self.logger.warning("Mode activation requested without a name")
            return False
        try:
            animation = create_animation(name, self.w, self.h)
        except Exception as exc:
            self.enqueue_event("mode.error", mode=name, message=str(exc), source=source)
            self.logger.error(f"Failed to activate mode '{name}': {exc}")
            return False
        if isinstance(animation, SolidColorAnimation):
            animation.set_color(self._solid_color_rgb)
        label = label or name
        self._set_animation(animation, base_name=name, label=label, source=source)
        return True

    def deactivate_mode(self, *, source: str = "ctrl") -> None:
        previous = self.current_mode or "?"
        self._install_fallback(source=source, emit_event=True)
        self.enqueue_event("mode.disabled", previous_mode=previous, source=source)

    def reset_mode(self, name: str | None = None, *, source: str = "ctrl") -> bool:
        target = (name or self.current_mode_name or "").strip()
        if not target:
            self.enqueue_event("mode.error", message="No mode available to reset", source=source)
            self.logger.warning("Reset requested without an active mode")
            return False
        self.enqueue_event("mode.reset", mode=target, source=source)
        if target.lower() == "solid_color":
            self._install_fallback(source=source, emit_event=True)
            return True
        return self.activate_mode(target, source=source)

    def _load_default_script(self):
        if not self.default_script:
            return
        self.logger.info(f"Loading default script: {self.default_script}")
        try:
            script_path = os.path.join(self.project_root, self.default_script)
            self.script = MscriptScript(script_path)
            self.enqueue_event("script.started", script=self.default_script, source="config")
            self.logger.info(f"Default script '{self.default_script}' loaded successfully.")
        except Exception as exc:
            self.enqueue_event("script.error", script=self.default_script, message=str(exc))
            self.logger.error(f"Failed to load default script '{self.default_script}': {exc}")

    def _process_node_command(self, command: str, parts: list[str]):
        if not parts:
            self.logger.debug(f"Ctrl: no command after node prefix in '{command}'")
            return

        cmd = parts[0].lower()
        self.logger.info(f"Ctrl: Received command: {command}")

        try:
            handler = self._command_handlers.get(cmd)
            if handler:
                handler(parts)
            else:
                self.enqueue_event("command.unknown", command=command)
                self.logger.warning(f"Ctrl: unknown command: {command}")
        except Exception as exc:
            self.enqueue_event("command.error", command=command, message=str(exc))
            self.logger.error(f"Error processing command '{command}': {exc}", exc_info=True)

    def _process_external_command(self, msg):
        """Process an incoming command from either ZMQ or a running script."""
        if isinstance(msg, Command):
            self._process_script_command(msg)
            return

        if not isinstance(msg, str):
            self.logger.warning(f"Ctrl: unsupported command type {type(msg)!r}")
            return

        # This method is now a legacy entry point for script commands
        self._process_node_command(msg, msg.strip().split())

    def _handle_mode_command(self, parts: list[str]):
        if len(parts) == 1:
            self.logger.info(f"Ctrl: current mode -> {self.current_mode}")
            return
        action = parts[1].lower()
        if action in {"on", "enable"}:
            target = " ".join(parts[2:]) if len(parts) >= 3 else (self.current_mode_name or "")
            if not target:
                self.enqueue_event("mode.error", message="Mode on requested without a target", source="ctrl")
                self.logger.warning("Mode on requested without a target")
                return
            self.activate_mode(target, source="ctrl")
        elif action in {"off", "disable"}:
            self.deactivate_mode(source="ctrl")
        elif action == "reset":
            target = " ".join(parts[2:]) if len(parts) >= 3 else None
            self.reset_mode(target, source="ctrl")
        else:
            name = " ".join(parts[1:])
            self.activate_mode(name, source="ctrl")

    def _handle_size_command(self, parts: list[str]):
        if len(parts) != 2 or "x" not in parts[1].lower():
            self.logger.warning(f"Ctrl: invalid size command: {' '.join(parts)}")
            return
        w_str, h_str = parts[1].lower().split("x", 1)
        new_w, new_h = int(w_str), int(h_str)
        self.w, self.h = new_w, new_h
        self.enqueue_event("size.changed", width=new_w, height=new_h, source="ctrl")
        self.logger.info(f"Ctrl: resized to {new_w}x{new_h}")
        if self.current_mode_name:
            label = self.current_mode or self.current_mode_name
            self.activate_mode(self.current_mode_name, source="ctrl", label=label)
        else:
            self._install_fallback(source="ctrl", emit_event=True)

    def _handle_color_command(self, parts: list[str]):
        color_args = parts[1:]
        target_mode = None

        def _is_int(val: str) -> bool:
            try:
                int(val)
                return True
            except (ValueError, TypeError):
                return False

        if color_args and not _is_int(color_args[0]):
            target_mode = color_args.pop(0).lower()
        if len(color_args) != 3:
            self.enqueue_event("color.error", message="Color command expects three components", source="ctrl")
            self.logger.warning(f"Ctrl: invalid color command args: {color_args}")
            return
        try:
            rgb = tuple(max(0, min(255, int(c))) for c in color_args)
        except ValueError:
            self.enqueue_event("color.error", message="Color components must be integers", source="ctrl")
            self.logger.warning(f"Ctrl: invalid color values: {color_args}")
            return

        if target_mode in {"solid", "solid_color", "solidcolor", "fallback"}:
            self._solid_color_rgb = rgb
            if isinstance(self.anim, SolidColorAnimation):
                self.anim.set_color(rgb)
            self.enqueue_event("color.changed", rgb=rgb, target="solid_color", source="ctrl")
            return

        if self.anim and hasattr(self.anim, "set_color"):
            self.anim.set_color(rgb)
            if isinstance(self.anim, SolidColorAnimation):
                self._solid_color_rgb = rgb
            self.enqueue_event("color.changed", rgb=rgb, source="ctrl")
        else:
            self.logger.warning("Ctrl: color command ignored; current animation has no set_color")

    def _handle_play_command(self, parts: list[str]):
        if len(parts) < 2:
            self.logger.warning("Ctrl: play command requires a script path")
            return
        script_rel = " ".join(parts[1:])
        path = os.path.join(self.project_root, script_rel)
        self.script = MscriptScript(path)
        self.enqueue_event("script.started", script=script_rel, source="ctrl")
        self.logger.info(f"Ctrl: Started script '{path}'")

    def _handle_stop_command(self, parts: list[str]):
        if self.script:
            self.logger.info("Ctrl: Script stopped by command")
            self.enqueue_event("script.stopped", source="ctrl")
            self.script = None

    def _process_script_command(self, command: Command):
        """Handle structured commands emitted by an active script."""
        name = (command.name or "").upper()
        args = dict(command.args or {})

        key_id = args.get("K")
        key_int = None
        if key_id is not None:
            try:
                key_int = int(key_id)
                args["K"] = key_int
            except (TypeError, ValueError):
                self.logger.warning(f"Script: invalid key id '{key_id}' for command {name}")
                key_int = None

        event_name = args.pop("EVENT", None)

        if event_name and key_int is not None:
            target_anim = self.keyframes.get(key_int)
            if not target_anim:
                self.logger.warning(f"Script: EVENT '{event_name}' for unknown key {key_int}")
                return
            try:
                payload_args = {k: v for k, v in args.items() if k != "K"}
                target_anim.on_event(event_name, **payload_args)
                self.anim = target_anim
                self.current_mode = f"{name}[{key_int}]"
                self.enqueue_event("animation.event", animation=self.current_mode, event=event_name, args=payload_args)
            except Exception as exc:
                self.enqueue_event("animation.error", animation=self.current_mode, message=str(exc))
                self.logger.error(f"Script: event '{event_name}' failed for key {key_int}: {exc}")
            return

        anim_kwargs = {k: v for k, v in args.items() if k != "K"}
        anim_kwargs["resolve_dir"] = self.project_root

        try:
            new_anim = create_animation(name, self.w, self.h, **anim_kwargs)
        except Exception as exc:
            self.enqueue_event("animation.error", animation=name, message=str(exc))
            self.logger.error(f"Script: failed to create animation '{name}' with args {anim_kwargs}: {exc}")
            return

        if key_int is not None:
            self.keyframes[key_int] = new_anim

        label = f"{name}[{key_int}]" if key_int is not None else name
        self._set_animation(new_anim, base_name=name, label=label, source="script")

    def _update_tick(self, timestamp):
        """Update the active script + drain LLM bus messages."""
        # ── drain SUB socket (non-blocking) ────────────────────────
        # LLM replies arrive here as Msg JSON envelopes.  We parse the
        # reply text for <play>/<mode>/<stop> tags and treat each
        # parsed command as if it came through the ctrl socket.
        if self._sub_socket is not None:
            while True:
                try:
                    topic, payload = self._sub_socket.recv_multipart(
                        flags=zmq.NOBLOCK,
                    )
                except zmq.Again:
                    break
                except Exception as exc:  # noqa: BLE001
                    self.logger.error(
                        "Error receiving from SUB: %s", exc,
                        exc_info=True,
                    )
                    break
                if topic not in self._subscribe_topics:
                    continue
                try:
                    msg = Msg.from_json(payload)
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning(
                        "Discarding malformed LLM payload: %s", exc,
                    )
                    continue
                self._handle_llm_reply(msg.text)

        # ── script tick (existing behaviour) ───────────────────────
        if self.script:
            due_commands = self.script.update(timestamp)
            for command in due_commands:
                self._process_external_command(command)

    def _handle_llm_reply(self, reply_text: str) -> None:
        """Parse an LLM reply for animation tags and dispatch each."""
        commands = _parse_llm_commands(reply_text)
        if not commands:
            return
        for cmd in commands:
            self._dispatch_llm_command(cmd)

    def _dispatch_llm_command(
        self,
        cmd: _LLMAnimationCommand,
    ) -> None:
        """Convert a parsed LLM command into the ctrl-socket text form
        and route through the existing _process_node_command path."""
        if cmd.verb == "stop":
            self._process_node_command("stop", ["stop"])
            self.enqueue_event(
                "llm.command", verb="stop", source="llm",
            )
            return

        if not cmd.name:
            return

        # Catalog lookup: if the LLM-emitted name lives in the
        # catalog AND points to an mscript, route as "play <path>".
        # Otherwise route as "mode <name>" — the renderer's existing
        # mode resolver handles animation modes registered in
        # animations/__init__.py.
        entry = self._catalog_index.get(cmd.name)
        if entry and entry.get("type") == "mscripts":
            asset_path = entry.get("path", "")
            text = f"play {asset_path}"
            parts = text.split()
            self._process_node_command(text, parts)
            self.enqueue_event(
                "llm.command", verb="play",
                name=cmd.name, path=asset_path, source="llm",
            )
            return

        # mode dispatch — works for animation defs, gif/sprite/math/
        # video/bitmap names registered in animations/__init__.py.
        text = f"mode {cmd.name}"
        parts = text.split()
        self._process_node_command(text, parts)
        self.enqueue_event(
            "llm.command", verb="mode",
            name=cmd.name, source="llm",
        )

    def _render_tick(self, timestamp):
        """Render the current animation into a pixel buffer."""
        if self.anim is None:
            return None
        
        zmq_manager.ensure_buffers(self.w, self.h)
        try:
            self.anim.render_into(timestamp, zmq_manager.pixel_buf)
        except Exception as exc:
            self.enqueue_event("frame.error", animation=self.current_mode, message=str(exc))
            self.logger.error(f"frame() error from '{self.current_mode}': {exc}")
            error_color_bytes = b"\x80\x00\x00"
            zmq_manager.pixel_buf[:] = error_color_bytes * (self.w * self.h)
        return zmq_manager.pixel_buf

    def on_shutdown(self) -> None:
        self.logger.info("AnimationNode-specific shutdown tasks can go here.")

class SolidColorAnimation(Animation):
    """A simple fallback animation that fills the screen with a solid color."""
    def __init__(self, w, h, color=(0, 0, 0)):
        super().__init__(w, h)
        self.set_color(color)

    def render_into(self, t: float, pixel_buf: bytearray):
        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        frame[:, :] = self.color

    def set_color(self, color: tuple[int, int, int] | list[int]):
        self.color = tuple(max(0, min(255, int(c))) for c in color)

def main():
    """The main function for the Mochi node."""
    logger = setup_logger("MochiNode")

    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Cannot load config.yaml: {e}")
        return

    config = config or {}
    env_cfg_raw = os.environ.get("MOCHI_PLUGIN_CONFIG_JSON")
    if env_cfg_raw:
        try:
            env_cfg = json.loads(env_cfg_raw)
            if isinstance(env_cfg, dict):
                config = _merge_dicts(config, env_cfg)
        except json.JSONDecodeError as exc:
            logger.warning(f"Invalid MOCHI_PLUGIN_CONFIG_JSON: {exc}")

    node_config = config.get("node", {})

    node_id = os.environ.get("MOCHI_NODE_ID") or node_config.get("id") or "animation"

    optional_topics_cfg = node_config.get("optional_topics", []) or []
    optional_topics_env = os.environ.get("MOCHI_NODE_OPTIONAL_TOPICS", "")
    if optional_topics_env:
        optional_topics_cfg = list(optional_topics_cfg) + [t.strip() for t in optional_topics_env.split(",") if t.strip()]
    optional_topics: list[bytes] = []
    for entry in optional_topics_cfg:
        if isinstance(entry, bytes):
            optional_topics.append(entry)
        elif isinstance(entry, str):
            optional_topics.append(entry.encode("utf-8"))
        else:
            logger.warning(f"Ignoring optional topic with unsupported type: {entry!r}")

    if optional_topics:
        optional_topics = list(dict.fromkeys(optional_topics))

    node = AnimationNode(node_id, node_config, PROJECT_ROOT_STR, optional_topics=optional_topics)

    node.run()

if __name__ == "__main__":
    main()
