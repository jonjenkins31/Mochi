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
from plugin_core.mochi_animations import Animation

# Project root, derived the same way node.py does (this file lives at
# nodes/animation/animations/math_handler.py, three levels below it).
# Used as the fallback confinement root when no resolve_dir is given.
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

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

        # Confinement: math assets are arbitrary Python that gets
        # exec'd, and asset_path is reachable from the ctrl socket.
        # Only load .py files that resolve under <project_root>/assets/math/.
        project_root = resolve_dir or _PROJECT_ROOT
        allowed_root = os.path.realpath(
            os.path.join(project_root, "assets", "math")
        )
        real_path = os.path.realpath(asset_path)
        if (not real_path.endswith(".py")
                or not real_path.startswith(allowed_root + os.sep)):
            print(
                f"Warning: MATH handler refusing asset_path '{asset_path}' — "
                f"must be a .py file under {allowed_root}."
            )
            return

        # Dynamically load the module and find the Animation class
        anim_class = None
        try:
            module_name = os.path.splitext(os.path.basename(real_path))[0]
            spec = importlib.util.spec_from_file_location(module_name, real_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Explicit export wins; otherwise pick the last
                # Animation subclass DEFINED in the module itself
                # (skips bases defined earlier and imported classes).
                explicit = getattr(module, "ANIMATION", None)
                if (isinstance(explicit, type)
                        and issubclass(explicit, Animation)
                        and explicit is not Animation):
                    anim_class = explicit
                else:
                    for attr in vars(module).values():
                        if (isinstance(attr, type)
                                and issubclass(attr, Animation)
                                and attr is not Animation
                                and attr.__module__ == module.__name__):
                            anim_class = attr  # last-defined wins
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
