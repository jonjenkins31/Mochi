# animations/__init__.py
# Auto-registry for Mochi animation plugins and media assets.

import importlib
import os
import logging
from typing import Dict, Type, List

from core.mochi_animations import Animation

# --- Logging ---
logger = logging.getLogger(__name__)

# --- Paths ---
# Get the absolute path to the directory of this file (__init__.py)
_ANIMATIONS_DIR = os.path.dirname(os.path.abspath(__file__))
# Get the project root directory (one level up)
_PROJECT_ROOT = os.path.dirname(_ANIMATIONS_DIR)

# --- Plugin Registry ---
_registry: Dict[str, Type[Animation]] = {}
_loaded = False

# --- Asset Discovery ---
_asset_paths: Dict[str, str] = {}
_assets_loaded = False
# ADDED 'assets/gifs' to the list of directories to scan
ASSET_DIRS = [
    os.path.join(_PROJECT_ROOT, "assets/images"), 
    os.path.join(_PROJECT_ROOT, "assets/icons"),
    os.path.join(_PROJECT_ROOT, "assets/gifs")
]
SUPPORTED_EXTS = [".gif", ".png", ".jpg", ".jpeg", ".bmp"]

def _discover_python_plugins() -> None:
    """Import all submodules in this package and register Animation subclasses."""
    global _loaded
    if _loaded:
        return
    _registry.clear()

    # Use os.listdir for more robust discovery than pkgutil
    for filename in os.listdir(_ANIMATIONS_DIR):
        if filename.endswith(".py") and not filename.startswith("__") and filename != "mochi_animations.py":
            module_name = filename[:-3] # remove .py
            try:
                mod_path = f"{__name__}.{module_name}"
                mod = importlib.import_module(mod_path)
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, Animation)
                        and obj is not Animation
                        and getattr(obj, "name", None)
                    ):
                        _registry[obj.name] = obj
            except Exception as e:
                logger.warning(f"Failed to load animation plugin '{module_name}': {e}")
    _loaded = True

def _discover_assets() -> None:
    """Scan asset directories for supported media files."""
    global _assets_loaded
    if _assets_loaded:
        return
    _asset_paths.clear()
    for asset_dir in ASSET_DIRS:
        if not os.path.isdir(asset_dir):
            continue
        for filename in os.listdir(asset_dir):
            name, ext = os.path.splitext(filename)
            if ext.lower() in SUPPORTED_EXTS:
                if name not in _registry:
                    _asset_paths[name] = os.path.join(asset_dir, filename)
    _assets_loaded = True

def list_names() -> List[str]:
    """Return sorted list of available python animations and media assets."""
    _discover_python_plugins()
    _discover_assets()
    all_names = set(_registry.keys()) | set(_asset_paths.keys())
    return sorted(list(all_names))


def create(name: str, w: int, h: int, **kwargs) -> Animation:
    """
    Instantiate an animation by name.
    If the name matches a Python animation class, it's created.
    If not, it searches for a matching media file in the assets directories
    and uses MediaPlayer to play it.
    """
    _discover_python_plugins()
    
    cls = _registry.get(name)
    if cls:
        inst = cls(w, h)
        inst.on_enter(**kwargs)
        return inst

    _discover_assets()
    asset_path = _asset_paths.get(name)
    if asset_path:
        logger.info(f"Found asset '{name}' at path: {asset_path}")
        try:
            from .media_player import MediaPlayer
            from core.media import decode_image

            media_frames = decode_image(asset_path, target_size=(w, h), fit_mode='fit')
            
            if not media_frames:
                raise ValueError(f"Failed to decode media file: {asset_path}")

            inst = MediaPlayer(w, h, frames=media_frames)
            inst.on_enter(**kwargs)
            return inst

        except Exception as e:
            logger.error(f"Error creating MediaPlayer for asset '{name}': {e}")
    
    raise KeyError(f"Unknown animation or asset '{name}'. Available: {', '.join(list_names())}")


def get_class(name: str) -> Type[Animation]:
    """Return the class for a Python animation name (advanced use)."""
    _discover_python_plugins()
    cls = _registry.get(name)
    if cls is None:
        raise KeyError(f"Unknown Python animation '{name}'. Available: {', '.join(sorted(_registry.keys()))}")
    return cls


def reload_plugins() -> None:
    """Force re-scan of Python plugins and media assets (useful during development)."""
    global _loaded, _assets_loaded
    _loaded = False
    _assets_loaded = False
    logger.info("Reloading plugins and assets.")
