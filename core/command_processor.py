# core/command_processor.py

"""
Handles processing of commands from scripts.
"""

import logging
from animations.master_handler import create_animation as create_anim
from core.mochi_script_engine import Command
from core.node_state import node_state

logger = logging.getLogger(__name__)

def process_command(cmd: Command, resolve_dir: str | None = None):
    """Executes a command received from a script."""
    try:
        if cmd.name == "event":
            ev_name = cmd.args.pop("name", None)
            if not ev_name:
                logger.warning("Script: event step missing 'name'")
                return
            if node_state.anim:
                node_state.anim.on_event(ev_name, **cmd.args)
            logger.info(f"Script: event -> {ev_name} {cmd.args if cmd.args else ''}")
        elif cmd.name == "stop_script":
            if node_state.script:
                logger.info("Script finished")
                node_state.script = None
        else:
            # All other commands are treated as animation/asset names
            try:
                args = cmd.args.copy()
                if resolve_dir:
                    args['resolve_dir'] = resolve_dir
                
                new = create_anim(cmd.name, node_state.w, node_state.h, **args)
                node_state.anim, node_state.current_mode = new, cmd.name
                logger.info(f"Script: loaded animation '{cmd.name}' with args {args}")
            except KeyError:
                 logger.warning(f"Script: unknown command or asset '{cmd.name}'")
    except Exception as e:
        logger.error(f"Script error processing step {cmd}: {e}")
