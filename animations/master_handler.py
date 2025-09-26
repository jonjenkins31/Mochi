# animations/master_handler.py
"""
Master Handler: The Central Animation Factory (v3.0)

This module acts as a universal factory for creating all animation instances.
It is the single point of entry for the Mochi node to request an animation.
It discovers registered handlers and can dynamically load python-based animations.
"""

import importlib.util
import os
import sys
import logging
from typing import Dict, Type, List

from core.mochi_animations import Animation

logger = logging.getLogger(__name__)

# Maps mscript commands to their corresponding handler names.
# The handler name is defined by the 'name' attribute in the handler's class.
COMMAND_TO_HANDLER_MAP = {
    "IMAGE": "media_handler",
    "MEDIA": "media_handler",
    "BITMAP": "bitmap_handler",
    "SPRITE": "sprite_handler",
}

class _AnimationFactory:
    """A singleton factory that discovers, registers, and creates animations."""
    def __init__(self):
        self._project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._python_plugin_dirs = [
            os.path.join(self._project_root, "animations"),
            os.path.join(self._project_root, "assets/math")
        ]
        self._registry: Dict[str, Type[Animation]] = {}
        self._loaded = False

    def _discover(self):
        if self._loaded:
            return
        self._registry.clear()
        self._discover_python_plugins()
        self._loaded = True

    def _discover_python_plugins(self):
        for plugin_dir in self._python_plugin_dirs:
            if not os.path.isdir(plugin_dir):
                continue
            for filename in os.listdir(plugin_dir):
                if filename.endswith('.py') and not filename.startswith('__') and filename != 'master_handler.py':
                    module_path = os.path.join(plugin_dir, filename)
                    module_name = os.path.splitext(filename)[0]
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            if module_name not in sys.modules:
                                sys.modules[module_name] = mod
                                spec.loader.exec_module(mod)
                            else:
                                mod = sys.modules[module_name]
                            
                            for attr in dir(mod):
                                obj = getattr(mod, attr)
                                if (isinstance(obj, type) and issubclass(obj, Animation) and
                                        obj is not Animation and getattr(obj, "name", None)):
                                    self._registry[obj.name] = obj
                    except Exception as e:
                        logger.warning(f"Failed to load animation plugin '{module_path}': {e}")

    def list_names(self) -> List[str]:
        self._discover()
        return sorted(list(self._registry.keys()))

    def create(self, cmd: str, w: int, h: int, **args) -> Animation:
        self._discover()

        handler_class = None
        
        if cmd == 'MATH':
            asset_path = args.get('asset_path')
            if not asset_path or not asset_path.endswith('.py'):
                raise ValueError("MATH command requires a valid 'asset_path' to a .py file.")
            
            module_name = os.path.splitext(os.path.basename(asset_path))[0]
            try:
                spec = importlib.util.spec_from_file_location(module_name, asset_path)
                if not spec or not spec.loader:
                    raise ImportError(f"Could not create module spec for {asset_path}")
                
                mod = importlib.util.module_from_spec(spec)
                if module_name not in sys.modules:
                    sys.modules[module_name] = mod
                    spec.loader.exec_module(mod)
                else:
                    mod = sys.modules[module_name]

                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if isinstance(obj, type) and issubclass(obj, Animation) and obj is not Animation:
                        handler_class = obj
                        break
                
                if not handler_class:
                    raise TypeError(f"No 'Animation' subclass found in script: {asset_path}")
            except Exception as e:
                logger.error(f"Failed to load MATH animation from '{asset_path}': {e}")
                raise

        else:
            handler_name = COMMAND_TO_HANDLER_MAP.get(cmd)
            if not handler_name:
                raise KeyError(f"The command '{cmd}' is not a valid or supported animation command.")
            
            handler_class = self._registry.get(handler_name)

        if not handler_class:
            raise KeyError(f"Could not find a handler for command '{cmd}'. Ensure it is registered.")

        inst = handler_class(w, h)
        inst.on_enter(**args)
        return inst

    def reload(self):
        self._loaded = False
        modules_to_remove = []
        for mod_name, mod in sys.modules.items():
            mod_file = getattr(mod, '__file__', None)
            if mod_file:
                for plugin_dir in self._python_plugin_dirs:
                    if mod_file.startswith(plugin_dir):
                        modules_to_remove.append(mod_name)
                        break
        
        for mod_name in modules_to_remove:
            del sys.modules[mod_name]

        logger.info("Reloading plugins and assets.")

# --- Singleton instance and public API --- 
_factory = _AnimationFactory()

create_animation = _factory.create
list_animation_names = _factory.list_names
reload_animations = _factory.reload
