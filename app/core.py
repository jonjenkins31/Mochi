"""Core — the Tier-1 main-thread host role.

A Core is distinct from a supervised worker Node and from a GUI Surface. It
initializes on the OS main thread during chassis boot, after the bus exists and
before nodes/surfaces start. Identity-critical local AI belongs here when the
backend cannot be constructed on a worker thread.
"""

from __future__ import annotations

import abc
import threading
from typing import Any


class CoreMainThreadError(RuntimeError):
    """A Tier-1 core was constructed off the OS main thread."""


class Core(abc.ABC):
    """Tier-1 host/core contract."""

    def __init__(self, *, bus: Any) -> None:
        if threading.current_thread() is not threading.main_thread():
            raise CoreMainThreadError(
                "Tier-1 core must initialize on the OS main thread "
                "(it is not a worker node)"
            )
        self.bus = bus

    def setup(self) -> None:
        """Subscribe/spawn work after construction. Called on main thread."""

    def stop(self) -> None:
        """Stop accepting work and release resources. Idempotent."""

    def health(self) -> dict[str, Any]:
        return {}


__all__ = ["Core", "CoreMainThreadError"]
