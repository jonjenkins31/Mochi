# animations/bitmap_handler.py

"""
Bitmap Handler: Renders 1-bit monochrome bitmap assets.

Function:
This handler is designed to parse and display 1-bit monochrome bitmap data.
It is invoked by the Master Handler for a 'BITMAP' command. The associated
asset is a JSON file containing 'width', 'height', and a 'data' array
representing the packed bitmap. The handler centers the bitmap on the display.

Inputs (via kwargs from Master Handler):
- asset_path (str): The absolute path to the JSON asset file.
- FG (list[int], optional): The RGB color for the 'on' pixels (1s).
  Defaults to white.
- BG (list[int], optional): The RGB color for the 'off' pixels (0s).
  Defaults to black.

Output:
- Renders the specified bitmap into the pixel buffer provided by the Mochi node.
"""

import numpy as np
import os
import json
from core.mochi_animations import Animation

class BitmapHandler(Animation):
    """
    An animation that renders raw 1-bit bitmap data loaded from a JSON asset file.
    """
    name = "BITMAP"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.bitmap_data: np.ndarray | None = None
        self.bitmap_w: int = 0
        self.bitmap_h: int = 0
        self.on_color = np.array([255, 255, 255], dtype=np.uint8)
        self.off_color = np.array([0, 0, 0], dtype=np.uint8)
        self._resolve_dir: str | None = None # For resolving relative asset paths

    def _load_from_path(self, path: str):
        """Loads bitmap data from a JSON asset file."""
        if not os.path.isabs(path) and self._resolve_dir:
            path = os.path.join(self._resolve_dir, path)
        
        try:
            with open(path, 'r') as f:
                asset_data = json.load(f)
            
            self.bitmap_w = int(asset_data.get("width", 0))
            self.bitmap_h = int(asset_data.get("height", 0))
            raw_data = asset_data.get("data", [])
            if raw_data:
                self.bitmap_data = np.array(raw_data, dtype=np.uint8)
            else:
                self.bitmap_data = None # Clear data if asset is empty

        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading bitmap asset from {path}: {e}")
            self.bitmap_data = None

    def on_enter(self, **kwargs):
        super().on_enter(**kwargs)

        self._resolve_dir = kwargs.get("resolve_dir")
        path = kwargs.get("asset_path")

        if path:
            self._load_from_path(path)
        else:
            print("Warning: BitmapHandler received no asset_path.")

        if "FG" in kwargs and isinstance(kwargs["FG"], list):
            self.on_color = np.array(kwargs["FG"], dtype=np.uint8)
        
        if "BG" in kwargs and isinstance(kwargs["BG"], list):
            self.off_color = np.array(kwargs["BG"], dtype=np.uint8)

    def render_into(self, t: float, pixel_buf: bytearray):
        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        frame[:, :] = self.off_color

        if self.bitmap_data is None or self.bitmap_w == 0 or self.bitmap_h == 0:
            return

        start_x = (self.w - self.bitmap_w) // 2
        start_y = (self.h - self.bitmap_h) // 2

        y_coords, x_coords = np.mgrid[0:self.h, 0:self.w]
        source_x = x_coords - start_x
        source_y = y_coords - start_y

        in_bounds = (source_x >= 0) & (source_x < self.bitmap_w) & \
                    (source_y >= 0) & (source_y < self.bitmap_h)

        valid_sx = source_x[in_bounds]
        valid_sy = source_y[in_bounds]
        
        bytes_per_row = (self.bitmap_w + 7) // 8
        byte_indices = valid_sy * bytes_per_row + (valid_sx // 8)
        bit_indices = 7 - (valid_sx % 8)
        
        valid_byte_indices_mask = byte_indices < len(self.bitmap_data)
        byte_indices = byte_indices[valid_byte_indices_mask]
        bit_indices = bit_indices[valid_byte_indices_mask]
        
        pixel_values = (self.bitmap_data[byte_indices] >> bit_indices) & 1
        
        on_pixels_mask = np.zeros_like(in_bounds, dtype=bool)
        temp_mask = np.zeros_like(in_bounds, dtype=bool)
        temp_mask[in_bounds] = valid_byte_indices_mask
        on_pixels_mask[temp_mask] = (pixel_values == 1)

        frame[on_pixels_mask] = self.on_color
