# animations/math_handler.py

"""
Math Handler: A dynamic loader for Python-based animations.

Function:
This handler is invoked for a 'MATH' command. It dynamically loads a Python
module containing an Animation class from the specified asset_path. It then
instantiates that class and delegates all rendering and event handling to it.
This allows for complex, code-driven animations to be created and run as part
of a script.

Inputs (to the on_enter method):
- asset_path (str): The path to the Python file containing the animation class.
- **kwargs: Any additional parameters are passed down to the loaded math
            animation's on_enter method.

Output:
- This handler does not return a value directly. It manages an internal
  'active_animation' and renders it to the pixel buffer provided by the node.
"""

import os
import importlib.util
from core.mochi_animations import Animation

class MathHandler(Animation):
    """
    A handler that dynamically loads, instantiates, and runs a Python-based
    animation from a specified file path.
    """
    name = "MATH"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.active_animation: Animation | None = None

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        
        asset_path = kwargs.get("asset_path")
        resolve_dir = kwargs.get("resolve_dir")

        if not asset_path:
            print("Warning: MATH handler received no asset_path.")
            return

        # Handle relative paths
        if not os.path.isabs(asset_path) and resolve_dir:
            asset_path = os.path.join(resolve_dir, asset_path)

        # Dynamically load the module and find the Animation class
        anim_class = None
        try:
            module_name = os.path.splitext(os.path.basename(asset_path))[0]
            spec = importlib.util.spec_from_file_location(module_name, asset_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    # Find the first class that is a subclass of Animation
                    if isinstance(attr, type) and issubclass(attr, Animation) and attr is not Animation:
                        anim_class = attr
                        break # Found it
        except Exception as e:
            print(f"Error loading math animation from {asset_path}: {e}")
            return

        if anim_class:
            self.active_animation = anim_class(self.w, self.h)
            # Pass all arguments down to the actual animation
            self.active_animation.on_enter(**kwargs)
        else:
            print(f"Warning: No Animation class found in {asset_path}")

    def on_event(self, event: str, **kwargs) -> None:
        if self.active_animation:
            self.active_animation.on_event(event, **kwargs)

    def render_into(self, t: float, pixel_buf: bytearray):
        if self.active_animation:
            self.active_animation.render_into(t, pixel_buf)
