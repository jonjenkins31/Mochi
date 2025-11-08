# animations/sprite_handler.py

"""
Sprite Handler: Displays individual sprites from a sprite sheet.

Function:
This handler is designed to work with sprite sheets, where a single image file
contains multiple smaller images or frames. It is invoked for a 'SPRITE' command.
It loads the sprite sheet from the asset_path and crops a single sprite from it
using the coordinates provided in the SRC argument.

Inputs (via kwargs from Master Handler):
- asset_path (str): Path to the sprite sheet image file.
- SRC (str): A comma-separated string defining the source rectangle of the
  sprite to display, in the format "x,y,w,h".

Output:
- Renders the selected sprite, cropped from the main sprite sheet, into the
  pixel buffer provided by the Mochi node.
"""

import os
from typing import Tuple
import numpy as np
from plugin_core.mochi_animations import Animation
from PIL import Image

class SpriteHandler(Animation):
    name = "SPRITE"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.sprite_sheet: Image.Image | None = None
        self.sprite_coords: Tuple[int, int, int, int] | None = None

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        
        resolve_dir = kwargs.get("resolve_dir")
        asset_path = kwargs.get("asset_path")
        src_rect_str = kwargs.get("SRC")

        if asset_path:
            try:
                if not os.path.isabs(asset_path) and resolve_dir:
                    asset_path = os.path.join(resolve_dir, asset_path)
                self.sprite_sheet = Image.open(asset_path).convert("RGB")
            except FileNotFoundError as e:
                print(f"Error loading sprite image: {e}")
                self.sprite_sheet = None
        
        if src_rect_str:
            try:
                coords = [int(c.strip()) for c in src_rect_str.split(',')]
                if len(coords) == 4:
                    self.sprite_coords = tuple(coords)
                else:
                    print(f"Warning: Invalid SRC format: {src_rect_str}")
            except (ValueError, AttributeError):
                print(f"Warning: Could not parse SRC rect: {src_rect_str}")

    def render_into(self, t: float, pixel_buf: bytearray):
        if not self.sprite_sheet or not self.sprite_coords:
            return

        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        if self.clear_on_frame:
            frame[:, :] = (0, 0, 0)  # Clear to black

        x, y, w, h = self.sprite_coords
        
        sprite_image = self.sprite_sheet.crop((x, y, x + w, y + h))
        sprite_array = np.array(sprite_image)
        img_h, img_w, _ = sprite_array.shape

        # Center the sprite
        start_x = (self.w - img_w) // 2
        start_y = (self.h - img_h) // 2

        # --- NumPy-based Blitting ---
        dest_y_start = max(0, start_y)
        dest_y_end = min(self.h, start_y + img_h)
        dest_x_start = max(0, start_x)
        dest_x_end = min(self.w, start_x + img_w)

        src_y_start = max(0, -start_y)
        src_y_end = src_y_start + (dest_y_end - dest_y_start)
        src_x_start = max(0, -start_x)
        src_x_end = src_x_start + (dest_x_end - dest_x_start)

        if dest_y_start < dest_y_end and dest_x_start < dest_x_end:
            # Ensure the source slice does not go out of bounds of the sprite array
            safe_src_y_end = min(sprite_array.shape[0], src_y_end)
            safe_src_x_end = min(sprite_array.shape[1], src_x_end)

            frame[dest_y_start:dest_y_end, dest_x_start:dest_x_end] = \
                sprite_array[src_y_start:safe_src_y_end, src_x_start:safe_src_x_end]
