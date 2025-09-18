# animations/__init__.py
# Auto-registry for Mochi animation plugins.

import importlib
import pkgutil
from typing import Dict, Type, List

from .base import Animation

_registry: Dict[str, Type[Animation]] = {}
_loaded = False


def _discover() -> None:
    """Import all submodules in this package and register Animation subclasses."""
    global _loaded
    if _loaded:
        return
    for m in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        mod_name = f"{__name__}.{m.name}"
        mod = importlib.import_module(mod_name)
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, Animation)
                and obj is not Animation
                and getattr(obj, "name", None)
            ):
                _registry[obj.name] = obj
    _loaded = True


def list_names() -> List[str]:
    """Return sorted list of available animation names."""
    _discover()
    return sorted(_registry.keys())


def create(name: str, w: int, h: int, **kwargs) -> Animation:
    """Instantiate an animation by name with size (w,h). kwargs passed to on_enter()."""
    _discover()
    cls = _registry.get(name)
    if cls is None:
        raise KeyError(f"Unknown animation '{name}'. Available: {', '.join(list_names())}")
    inst = cls(w, h)
    inst.on_enter(**kwargs)
    return inst


def get_class(name: str) -> Type[Animation]:
    """Return the class for an animation name (advanced use)."""
    _discover()
    cls = _registry.get(name)
    if cls is None:
        raise KeyError(f"Unknown animation '{name}'. Available: {', '.join(list_names())}")
    return cls


def reload_plugins() -> None:
    """Force re-scan (useful during development)."""
    global _loaded
    _loaded = False
    _registry.clear()
    _discover()