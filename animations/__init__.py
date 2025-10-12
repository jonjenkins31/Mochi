# animations/__init__.py
"""
This package contains all the animation handlers for Mochi, as well as the
master factory for creating them.

The public API of this package is defined by the functions exposed here.
"""

import logging
from importlib import reload
from typing import Dict, Type, List

from core.mochi_animations import Animation
# Import modules to allow for registration and reloading
from . import bitmap_handler
from . import media_handler
from . import sprite_handler
from . import math_handler

logger = logging.getLogger(__name__)

class _AnimationFactory:
    """A singleton factory that registers and creates animations."""
    def __init__(self):
        self._registry: Dict[str, Type[Animation]] = {}
        self._handler_modules = [bitmap_handler, media_handler, sprite_handler, math_handler]
        self._register_handlers()

    def _register_handlers(self):
        """(Re)registers all the known animation handlers from the imported modules."""
        self._registry.clear()
        # It's better to access the name via the class property to avoid errors
        # if the handler isn't a class with a 'name' attribute.
        self._registry[bitmap_handler.BitmapHandler.name] = bitmap_handler.BitmapHandler
        self._registry[media_handler.MediaHandler.name] = media_handler.MediaHandler
        self._registry[sprite_handler.SpriteHandler.name] = sprite_handler.SpriteHandler
        self._registry[math_handler.MathHandler.name] = math_handler.MathHandler

    def list_names(self) -> List[str]:
        """Returns a list of all registered animation command names."""
        return sorted(list(self._registry.keys()))

    def create(self, cmd: str, w: int, h: int, **args) -> Animation:
        """
        Creates an instance of the appropriate animation handler for the given command.
        """
        handler_class = self._registry.get(cmd)

        if not handler_class:
            raise KeyError(f"The command '{cmd}' is not a valid or supported animation command.")

        # Instantiate the handler and call its on_enter method with all arguments
        inst = handler_class(w, h)
        inst.on_enter(**args)
        return inst

    def reload(self):
        """
        Reloads all handler modules to pick up code changes during development.
        """
        logger.info("Reloading animation handlers...")
        for mod in self._handler_modules:
            try:
                reload(mod)
            except Exception as e:
                logger.error(f"Failed to reload module {mod.__name__}: {e}")

        # Re-register the (potentially new) classes from the reloaded modules
        self._register_handlers()
        logger.info(f"Handlers reloaded. Registered: {self.list_names()}")


# --- Singleton instance and public API ---
_factory = _AnimationFactory()

create_animation = _factory.create
list_animation_names = _factory.list_names
reload_animations = _factory.reload

__all__ = [
    'create_animation',
    'list_animation_names',
    'reload_animations'
]
