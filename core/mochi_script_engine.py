# core/mochi_script_engine.py
# Pluggable engine for parsing and running command scripts.

import time
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, NamedTuple

# A command is a simple structure for what the node should do.
class Command(NamedTuple):
    name: str
    args: Dict[str, Any]

# --- Abstract Base Class for all Scripts ---
class Script(ABC):
    """
    Abstract base class for a runnable script.
    A script is an object that returns commands for the node to execute
    based on the current time.
    """
    def __init__(self, path: str):
        self.path = path
        self.start_time = time.time()

    @abstractmethod
    def update(self, t: float) -> List[Command]:
        """
        Given the current time `t`, return a list of any commands
        that are due to be executed.
        """
        raise NotImplementedError

# --- V3.0 JSON Timeline Implementation (mscript-aligned) ---
class JsonTimelineScript(Script):
    """
    The V3.0 script implementation that reads from a JSON file
    with a 'timeline' and 'resources' array.
    """
    def __init__(self, path: str):
        super().__init__(path)
        self._timeline = []
        self._resources: Dict[int, str] = {}
        self._index = 0
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

    def _get_resource_path(self, key: int) -> str:
        return self._resources.get(key)

    def update(self, t: float) -> List[Command]:
        elapsed = t - self.start_time
        due_commands = []
        
        while self._index < len(self._timeline) and elapsed >= self._timeline[self._index]["at"]:
            step = self._timeline[self._index]
            self._index += 1
            
            # Use "command" key, do not convert to lower
            cmd_name = step.get("command", "")
            if not cmd_name:
                continue

            args = step.get("args", {})

            # Resolve resource key if present
            if "K" in args:
                resource_path = self._get_resource_path(args["K"])
                if resource_path:
                    args["asset_path"] = resource_path
                else:
                    print(f"Warning: Resource key {args['K']} not found in resources.")
                    continue

            # The 'stop' command is special, it stops this script.
            if cmd_name.lower() == "stop":
                due_commands.append(Command(name="stop_script", args={}))
                break
            else:
                due_commands.append(Command(name=cmd_name, args=args))
                
        return due_commands

# --- Factory ---
def load_script(path: str) -> Script:
    """
    Factory function to load a script from a given path.
    It will eventually detect the script type, but for now,
    it only knows about the JSON timeline format.
    """
    if path.lower().endswith('.json'):
        return JsonTimelineScript(path)
    else:
        raise ValueError(f"Unknown script format for path: {path}")
