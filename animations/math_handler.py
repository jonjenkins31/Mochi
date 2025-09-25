# animations/math_handler.py

"""
Math Handler: A sub-factory for math-based animations.

Function:
This handler acts as a factory specifically for animations located in the
'assets/math' directory. It dynamically loads a Python-based animation from
that folder and delegates rendering to it.

NOTE: This handler is now largely a legacy component. The Master Handler can
load these animations directly, which is more efficient. For example, instead
of 'mode math name=bars', you can just use 'mode bars'.

Inputs (to the on_enter method):
- name (str): The name of the math animation to be loaded (e.g., 'bars').
- **kwargs: Any additional parameters are passed down to the selected
            math animation.

Output:
- This handler does not return a value directly. It manages an internal
  'active_animation' and renders it to the pixel buffer provided by the node.
"""

import os
import importlib.util
import numpy as np
from core.mochi_animations import Animation
from core.gfx import parse_color

class MathHandler(Animation):
    """
    A handler that dynamically loads and manages math-based animations
    from the assets/math directory.
    """
    name = "math"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.active_animation: Animation | None = None
        self._animation_classes = self._load_animation_classes()

    def _load_animation_classes(self):
        animation_classes = {}
        math_assets_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'math')

        for filename in os.listdir(math_assets_path):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]
                module_path = os.path.join(math_assets_path, filename)
                
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    for attr_name in dir(mod):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(attr, Animation) and attr is not Animation:
                            # Use the class's `name` attribute if it exists, otherwise use the module name
                            anim_name = getattr(attr, 'name', module_name)
                            animation_classes[anim_name] = attr
        return animation_classes

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        math_name = kwargs.get("name")
        if not math_name:
            return

        anim_class = self._animation_classes.get(math_name)
        if anim_class:
            self.active_animation = anim_class(self.w, self.h)
            self.active_animation.on_enter(**kwargs)

    def on_event(self, event: str, **kwargs) -> None:
        if self.active_animation:
            self.active_animation.on_event(event, **kwargs)

    def render_into(self, t: float, pixel_buf: bytearray):
        if self.active_animation:
            self.active_animation.render_into(t, pixel_buf)
