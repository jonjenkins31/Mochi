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

# --- V1.0 JSON Timeline Implementation ---
class JsonTimelineScript(Script):
    """
    The V1.0 script implementation that reads from a JSON file
    with a 'timeline' array.
    """
    def __init__(self, path: str):
        super().__init__(path)
        self._timeline = []
        self._index = 0
        self._load()

    def _load(self):
        with open(self.path, "r") as f:
            data = json.load(f)
        if "timeline" not in data:
            raise ValueError("script missing 'timeline' list")
        # Sort timeline by 'at' time
        self._timeline = sorted(data["timeline"], key=lambda s: float(s.get("at", 0.0)))

    def update(self, t: float) -> List[Command]:
        elapsed = t - self.start_time
        due_commands = []
        
        while self._index < len(self._timeline) and elapsed >= self._timeline[self._index]["at"]:
            step = self._timeline[self._index]
            self._index += 1
            
            cmd_name = step.get("cmd", "").lower()
            if not cmd_name:
                continue

            # The 'stop' command is special, it stops this script.
            if cmd_name == "stop":
                # Return a special command that the node will use to stop the script.
                due_commands.append(Command(name="stop_script", args={}))
                # Stop processing further steps in this script
                break
            else:
                due_commands.append(Command(name=cmd_name, args=step.get("args", {})))
                
        return due_commands

# --- Factory ---
def load_script(path: str) -> Script:
    """
    Factory function to load a script from a given path.
    It will eventually detect the script type, but for V1.0,
    it only knows about the JSON timeline format.
    """
    # For now, we only have one script type.
    # In the future, we could inspect the file extension or contents
    # to decide which Script class to instantiate.
    if path.lower().endswith('.json'):
        return JsonTimelineScript(path)
    else:
        raise ValueError(f"Unknown script format for path: {path}")
