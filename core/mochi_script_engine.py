# core/mochi_script_engine.py
# Pluggable engine for parsing and running JSON command scripts.

import json

# Import base classes from the new neutral location
from .mochi_animations import Script, Command
# Import the Mscript engine so the factory can use it
from .mscript_engine import MscriptScript

# --- V3.0 JSON Timeline Implementation ---
class JsonTimelineScript(Script):
    """
    The V3.0 script implementation that reads from a JSON file
    with a 'timeline' and 'resources' array.
    """
    def __init__(self, path: str):
        super().__init__(path)
        self._timeline = []
        self._resources: dict[int, str] = {}
        self._index = 0
        # A set of argument keys that are known to be colors and need parsing.
        self._color_keys = {'FG', 'BG', 'CLR', 'CLR2'}
        self._load()

    def _load(self):
        with open(self.path, "r") as f:
            data = json.load(f)
        
        if "timeline" not in data:
            raise ValueError("script missing 'timeline' list")
        
        if "resources" in data:
            for resource in data["resources"]:
                self._resources[resource["id"]] = resource["path"]

        # Sort timeline by 'at' time
        self._timeline = sorted(data["timeline"], key=lambda s: float(s.get("at", 0.0)))

    def _get_resource_path(self, key: int) -> str | None:
        return self._resources.get(key)

    def update(self, t: float) -> list[Command]:
        elapsed = t - self.start_time
        due_commands = []
        
        while self._index < len(self._timeline) and elapsed >= self._timeline[self._index]["at"]:
            step = self._timeline[self._index]
            self._index += 1
            
            cmd_name = step.get("command", "")
            if not cmd_name:
                continue

            args = step.get("args", {})

            # --- NEW: Normalize color arguments to integer lists ---
            for key in self._color_keys:
                if key in args and isinstance(args[key], str):
                    try:
                        args[key] = [int(c) for c in args[key].split()]
                    except (ValueError, AttributeError):
                        print(f"Warning: Could not parse color string '{args[key]}' for key '{key}'")

            # Resolve resource key if present
            if "K" in args:
                resource_path = self._get_resource_path(args["K"])
                if resource_path:
                    args["asset_path"] = resource_path
                else:
                    print(f"Warning: Resource key {args['K']} not found in resources.")
                    continue

            due_commands.append(Command(name=cmd_name, args=args))
                
        return due_commands

# --- Universal Script Factory ---
def load_script(path: str) -> Script:
    """
    Factory function to load a script from a given path.
    It detects the script type based on the file extension and returns the
    appropriate script engine instance.
    """
    if path.lower().endswith('.json'):
        return JsonTimelineScript(path)
    elif path.lower().endswith('.mscript'):
        return MscriptScript(path)
    else:
        raise ValueError(f"Unknown script format for path: {path}")
