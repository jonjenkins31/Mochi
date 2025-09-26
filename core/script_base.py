# core/script_base.py

"""
Contains the fundamental base classes for the Mochi scripting system.
"""

import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any, NamedTuple


class Command(NamedTuple):
    """A simple structure representing a command for the node to execute."""
    name: str
    args: Dict[str, Any]


class Script(ABC):
    """
    Abstract base class for a runnable script. A script is an object that
    returns commands for the node to execute based on the current time.
    """
    def __init__(self, path: str):
        self.path = path
        self.start_time = time.time()

    @abstractmethod
    def update(self, t: float) -> List[Command]:
        """
        Given the current time `t`, return a list of any commands that are due
        to be executed.
        """
        raise NotImplementedError
