# core/mochi_animations.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any, NamedTuple

# --- Base class for all Commands ---
class Command(NamedTuple):
    """A simple structure for what the node should do."""
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
        import time
        self.path = path
        self.start_time = time.time()

    @abstractmethod
    def update(self, t: float) -> List[Command]:
        """
        Given the current time `t`, return a list of any commands
        that are due to be executed.
        """
        raise NotImplementedError

# --- Abstract Base Class for all Animations ---
class Animation(ABC):
    """
    Abstract base class for a renderable animation.
    An animation is an object that can render its state into a pixel buffer.
    """
    name: str | None = None

    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.clear_on_frame = True

    def on_enter(self, **kwargs) -> None:
        """Called when the animation is first activated."""
        pass

    def on_event(self, event: str, **kwargs) -> None:
        """Called when the animation receives a script event."""
        pass

    def set_size(self, w: int, h: int):
        """Called when the logical display size changes."""
        self.w = w
        self.h = h

    @abstractmethod
    def render_into(self, t: float, pixel_buf: bytearray):
        """
        Given the current time `t`, render the animation state into the
        provided pixel buffer.
        """
        raise NotImplementedError
