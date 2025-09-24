# core/mscript_engine.py

import os
import re
import time
from typing import List, Dict, Any

# Import base classes from the original engine
from .mochi_script_engine import Script, Command

# --- V2.0 Mscript Parser ---
class _MscriptParser:
    """Internal class to parse a .mscript file."""
    def __init__(self, script_path: str):
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"MochiScript file not found: {script_path}")
        self.script_path = script_path
        self.instructions = []
        self.labels = {}
        self.resources = {}
        self._parse()

    def _parse(self):
        with open(self.script_path, 'r') as f:
            lines = f.readlines()

        in_resources_section = False
        current_line_num = 0

        for line in lines:
            current_line_num += 1
            stripped_line = line.strip()

            if not stripped_line or stripped_line.startswith('!'):
                continue # Skip empty lines and comments

            if stripped_line == '@RESOURCES':
                in_resources_section = True
                continue

            if in_resources_section:
                self._parse_resource_line(stripped_line)
            else:
                self._parse_instruction_line(stripped_line, current_line_num)

    def _parse_resource_line(self, line: str):
        # Corrected regex to handle both single and double quotes robustly.
        match = re.match(r"K\[(\d+):([^]]+)\]:\s*(?:'([^']*)'|\"([^\"]*)\")", line)
        if not match:
            raise ValueError(f"Malformed resource line: {line}")
        
        res_id_num, res_name, res_path_single, res_path_double = match.groups()
        # Correctly select the path, handling empty paths.
        res_path = res_path_single if res_path_single is not None else res_path_double
        full_id = f"K[{res_id_num}:{res_name}]"
        
        # Resolve the resource path relative to the script file.
        base_dir = os.path.dirname(self.script_path)
        self.resources[full_id] = os.path.abspath(os.path.join(base_dir, res_path.strip()))

    def _parse_instruction_line(self, line: str, line_num: int):
        if line.startswith('LBL['):
            match = re.match(r'LBL\[(\d+)(?::([^\]]+))?\]', line)
            if not match:
                raise ValueError(f"Malformed label line: {line}")
            label_id = int(match.group(1))
            self.labels[label_id] = len(self.instructions)
        else:
            parts = line.split(maxsplit=2)
            command = parts[0].upper()

            if command == 'JMP':
                match = re.match(r'LBL\[(\d+)\]', parts[1])
                if not match:
                    raise ValueError(f"Malformed JMP argument: {parts[1]}")
                self.instructions.append({
                    'type': 'JMP',
                    'asset_id': None,
                    'args': {'lbl': [int(match.group(1))]},
                    'original_line': line_num
                })
                return

            if len(parts) < 2:
                raise ValueError(f"Malformed instruction line: {line}")
            
            asset_id_str = parts[1]
            args_str = parts[2] if len(parts) > 2 else ""
            args = self._parse_arguments(args_str)
            
            self.instructions.append({
                'type': command,
                'asset_id': asset_id_str,
                'args': args,
                'original_line': line_num
            })

    def _parse_arguments(self, args_str: str) -> dict:
        args = {}
        arg_matches = re.findall(r'([A-Z]+)\[([^\]]+)\]', args_str)
        for key, value_str in arg_matches:
            values = []
            for v in value_str.split(','):
                v_strip = v.strip()
                try:
                    values.append(int(v_strip))
                except ValueError:
                    try:
                        values.append(float(v_strip))
                    except ValueError:
                        values.append(v_strip)
            args[key.lower()] = values
        return args

# --- V2.0 Mscript Engine ---
class MscriptScript(Script):
    """
    The V2.0 script implementation that reads and executes a .mscript file.
    This engine processes one instruction at a time, waiting for a specified
    duration before proceeding to the next.
    """
    def __init__(self, path: str):
        super().__init__(path)
        parser = _MscriptParser(path)
        self._instructions = parser.instructions
        self._labels = parser.labels
        self._resources = parser.resources
        
        self._program_counter = 0
        self._wait_until = 0.0

    def update(self, t: float) -> List[Command]:
        if self._program_counter >= len(self._instructions):
            return [Command(name="stop_script", args={})]

        if t < self._wait_until:
            return []

        instruction = self._instructions[self._program_counter]
        self._program_counter += 1

        cmd_type = instruction['type']
        args = instruction['args'].copy()
        asset_id = instruction['asset_id']

        if cmd_type == 'JMP':
            lbl_id = args['lbl'][0]
            if lbl_id in self._labels:
                self._program_counter = self._labels[lbl_id]
                return self.update(t)  # Execute next instruction immediately
            else:
                return [Command(name="stop_script", args={'error': f'Label {lbl_id} not found'})]

        duration = 0.0
        if 'd' in args:
            duration = float(args['d'][0])
            del args['d']
        
        self._wait_until = t + duration

        # Add asset info to the command arguments
        if asset_id:
            args['asset_id'] = asset_id
            if asset_id in self._resources:
                args['path'] = self._resources[asset_id]

        return [Command(name=cmd_type.lower(), args=args)]

# --- Factory (for this engine only) ---
def load_mscript(path: str) -> MscriptScript:
    """
    Factory function to load an mscript from a given path.
    """
    if path.lower().endswith('.mscript'):
        return MscriptScript(path)
    else:
        raise ValueError(f"Not an mscript file: {path}")
