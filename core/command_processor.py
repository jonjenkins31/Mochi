# core/command_processor.py

"""
Handles processing of commands from scripts.
"""

import logging
from animations import create_animation
# Import Command from its new, neutral location
from core.mochi_animations import Command
from core.node_state import node_state

logger = logging.getLogger(__name__)

def process_command(cmd: Command, resolve_dir: str | None = None):
    """Executes a command received from a script."""
    try:
        args = cmd.args.copy()
        event_name = args.pop("EVENT", None)

        # If there's an event, send it to the active animation
        if event_name:
            # Check if the command is targeting the currently active animation type
            if node_state.current_mode and cmd.name.upper() == node_state.current_mode.upper():
                if node_state.anim:
                    node_state.anim.on_event(event_name, **args)
                    logger.info(f"Script: event '{event_name}' -> {node_state.current_mode} with {args if args else ''}")
                else:
                    logger.warning(f"Script: received event '{event_name}' but no animation is active.")
            else:
                logger.warning(f"Script: received event for '{cmd.name}' but '{node_state.current_mode}' is active. Ignoring.")
        
        # If there's no event, it's a command to load a new animation
        else:
            if resolve_dir:
                args['resolve_dir'] = resolve_dir
            
            new_anim = create_animation(cmd.name, node_state.w, node_state.h, **args)
            node_state.anim = new_anim
            node_state.current_mode = cmd.name
            logger.info(f"Script: loaded animation '{cmd.name}' with args {args}")

    except Exception as e:
        logger.error(f"Error processing command '{cmd.name}' with args {cmd.args}: {e}", exc_info=True)
