# animations/master_handler.py

"""
Master Handler: The Central Animation Factory

Function:
This module acts as a universal factory for creating all animation and asset
instances. It is the single point of entry for the Mochi node to request
an animation. It discovers, registers, and instantiates the correct handler.

Inputs (to the create_animation function):
- cmd (str): The name of the handler or Python animation to use (e.g.,
  'media_handler', 'bitmap_handler', 'bars').
- w (int): The width of the display surface.
- h (int): The height of the display surface.
- **args: A dictionary of optional parameters. If a generic handler is used,
          this should contain a 'name' key with the asset's name.

Output (from the create_animation function):
- An instantiated animation object that is a subclass of the base 'Animation'
  class. This object is ready to be rendered.
"""

import importlib.util
import os
import sys
import logging
from typing import Dict, Type, List

from core.mochi_animations import Animation

logger = logging.getLogger(__name__)

class _AnimationFactory:
    """A singleton factory that discovers, registers, and creates animations."""
    def __init__(self):
        self._project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._python_plugin_dirs = [
            os.path.join(self._project_root, "animations"),
            os.path.join(self._project_root, "assets/math")
        ]
        self._asset_dirs = [
            os.path.join(self._project_root, "assets/images"),
            os.path.join(self._project_root, "assets/icons"),
            os.path.join(self._project_root, "assets/gifs"),
            os.path.join(self._project_root, "assets/bitmaps")
        ]
        self._supported_exts = [".gif", ".png", ".jpg", ".jpeg", ".bmp", ".json"]

        self._registry: Dict[str, Type[Animation]] = {}
        self._asset_paths: Dict[str, str] = {}
        self._loaded = False

    def _discover(self):
        if self._loaded:
            return
        self._registry.clear()
        self._asset_paths.clear()
        self._discover_python_plugins()
        self._discover_assets()
        self._loaded = True

    def _discover_python_plugins(self):
        for plugin_dir in self._python_plugin_dirs:
            if not os.path.isdir(plugin_dir):
                continue
            for filename in os.listdir(plugin_dir):
                if filename.endswith('.py') and not filename.startswith('__') and filename != 'master_handler.py':
                    rel_dir = os.path.relpath(plugin_dir, self._project_root)
                    package_name = rel_dir.replace(os.path.sep, '.')
                    module_name = f"{package_name}.{os.path.splitext(filename)[0]}"
                    module_path = os.path.join(plugin_dir, filename)
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            sys.modules[module_name] = mod
                            spec.loader.exec_module(mod)
                            for attr in dir(mod):
                                obj = getattr(mod, attr)
                                if (isinstance(obj, type) and issubclass(obj, Animation) and
                                        obj is not Animation and getattr(obj, "name", None)):
                                    self._registry[obj.name] = obj
                    except Exception as e:
                        logger.warning(f"Failed to load animation plugin '{module_path}': {e}")

    def _discover_assets(self):
        for asset_dir in self._asset_dirs:
            if not os.path.isdir(asset_dir):
                continue
            for filename in os.listdir(asset_dir):
                name, ext = os.path.splitext(filename)
                if ext.lower() in self._supported_exts:
                    if name not in self._registry:
                        self._asset_paths[name] = os.path.join(asset_dir, filename)

    def list_names(self) -> List[str]:
        self._discover()
        # Return handler names and asset names
        all_names = set(self._registry.keys()) | set(self._asset_paths.keys())
        return sorted(list(all_names))

    def create(self, cmd: str, w: int, h: int, **args) -> Animation:
        self._discover()

        lookup_key = cmd
        if cmd == 'math':
            lookup_key = args.get('name')
            if not lookup_key:
                raise ValueError("The 'math' command requires a 'name' argument to specify the animation.")
        
        handler_class = self._registry.get(lookup_key)

        if not handler_class:
            raise KeyError(f"Unknown handler or animation command '{lookup_key}'.")

        # If a named asset is required, resolve its path. This is for handlers
        # like `media_handler` that get a `name` argument for an asset file.
        asset_name = args.get("name")
        if asset_name:
            asset_path = self._asset_paths.get(asset_name)
            if asset_path:
                args['path'] = asset_path
                args['resolve_dir'] = os.path.dirname(asset_path)
        
        # Instantiate the handler with all the arguments
        inst = handler_class(w, h)
        inst.on_enter(**args)
        return inst

    def reload(self):
        self._loaded = False
        logger.info("Reloading plugins and assets.")

# --- Singleton instance and public API --- 
_factory = _AnimationFactory()

create_animation = _factory.create
list_animation_names = _factory.list_names
reload_animations = _factory.reload
