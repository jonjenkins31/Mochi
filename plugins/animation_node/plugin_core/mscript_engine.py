# core/mscript_engine.py

import os
import re

# Import base classes from the new neutral location
from .mochi_animations import Script, Command

# --- Mscript Parser (v3.0) ---
class _MscriptParser:
    """Parses a .mscript file into resources and a list of main instructions."""
    def __init__(self, script_path: str):
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"MochiScript file not found: {script_path}")
        
        self.instructions: list[dict[str, any]] = []
        self.resources: dict[int, str] = {}
        # A set of argument keys that are known to be colors and need parsing.
        self._color_keys = {'FG', 'BG', 'CLR', 'CLR2'}
        self._parse(script_path)

    def _parse(self, path: str):
        with open(path, 'r') as f:
            lines = f.readlines()

        current_section = None
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('!'):
                continue

            # Check for section changes
            section_match = re.match(r'^\[(Header|Resources|Main) (start|end)\]$', stripped)
            if section_match:
                section, state = section_match.groups()
                current_section = section if state == 'start' else None
                continue

            if current_section == 'Resources':
                self._parse_resource_line(stripped)
            elif current_section == 'Main':
                self._parse_main_line(stripped)

    def _parse_resource_line(self, line: str):
        match = re.match(r"K\[(\d+)\]:\s*'([^']+)'", line)
        if match:
            res_id, res_path = match.groups()
            self.resources[int(res_id)] = res_path

    def _parse_main_line(self, line: str):
        parts = line.split(maxsplit=1)
        command = parts[0].upper()
        args_str = parts[1] if len(parts) > 1 else ""

        # Regex to find all KEY[value] pairs
        arg_matches = re.findall(r'([A-Z_]+)\[([^\]]*)\]', args_str)
        args = {key: val for key, val in arg_matches}

        # --- NEW: Normalize color arguments to integer lists ---
        for key in self._color_keys:
            if key in args and isinstance(args[key], str):
                try:
                    args[key] = [int(c.strip()) for c in args[key].split(',')]
                except (ValueError, AttributeError):
                    print(f"Warning: Could not parse color string '{args[key]}' for key '{key}'")
        
        self.instructions.append({'command': command, 'args': args})


# --- Mscript Engine (v3.0) ---
class MscriptScript(Script):
    """
    The V3.0 script implementation that reads and executes a .mscript file.
    It correctly handles the line-by-line flow control using WAIT commands.
    """
    def __init__(self, path: str):
        super().__init__(path)
        parser = _MscriptParser(path)
        self._instructions = parser.instructions
        self._resources = parser.resources
        
        self._program_counter = 0
        self._wait_until = 0.0

    def update(self, t: float) -> list[Command]:
        if self._program_counter >= len(self._instructions):
            return [] # End of script

        if t < self._wait_until:
            return [] # Still waiting

        # Process all due commands until a WAIT is found
        due_commands: list[Command] = []
        while self._program_counter < len(self._instructions):
            instruction = self._instructions[self._program_counter]
            self._program_counter += 1

            cmd_name = instruction['command']
            args = instruction['args'].copy()

            # Handle WAIT command for timing control
            if cmd_name == 'WAIT':
                wait_duration = float(args.get('D', 0.0))
                self._wait_until = t + wait_duration
                # Stop processing for this frame and wait
                return due_commands

            # For all other commands, resolve the resource key if present
            if 'K' in args:
                key = int(args['K'])
                resource_path = self._resources.get(key)
                if resource_path:
                    # Add asset_path to the arguments, just like the JSON engine
                    args['asset_path'] = resource_path
                else:
                    print(f"Warning: Resource key {key} not found in resources.")
                    continue # Skip this invalid command
            
            due_commands.append(Command(name=cmd_name, args=args))

        return due_commands
