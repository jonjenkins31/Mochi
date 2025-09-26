# animations/__init__.py
"""
This package contains all the animation handlers for Mochi, as well as the
master factory for creating them.

The public API of this package is defined by the functions exposed from the
master_handler module.
"""

from .master_handler import create_animation, list_animation_names, reload_animations

__all__ = [
    'create_animation',
    'list_animation_names',
    'reload_animations'
]
