
import json
import os
from typing import List, Tuple
import numpy as np
from core.mochi_animations import Animation
from PIL import Image

class SpriteHandler(Animation):
    name = "sprite_handler"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.sprite_sheet = None
        self.sprites: List[Tuple[int, int, int, int]] = []
        self.current_sprite_index = 0

    def _load_config(self, config_path: str, base_path: str | None):
        """Loads the sprite animation configuration from a JSON file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            image_path = config.get("image_path")
            if image_path:
                # Resolve path relative to the config file's directory
                if not os.path.isabs(image_path) and base_path:
                    image_path = os.path.join(base_path, image_path)
                self.sprite_sheet = Image.open(image_path).convert("RGB")
            
            self.sprites = config.get("sprites", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading sprite config: {e}")
            self.sprite_sheet = None
            self.sprites = []

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        
        resolve_dir = kwargs.get("resolve_dir")
        config_path = kwargs.get("config_path")
        image_path = kwargs.get("image_path")
        sprites = kwargs.get("sprites")

        base_path = resolve_dir

        if config_path:
            if not os.path.isabs(config_path) and resolve_dir:
                config_path = os.path.join(resolve_dir, config_path)
            
            base_path = os.path.dirname(config_path)
            self._load_config(config_path, base_path)

        elif image_path and sprites is not None:
            try:
                if not os.path.isabs(image_path) and base_path:
                    image_path = os.path.join(base_path, image_path)
                self.sprite_sheet = Image.open(image_path).convert("RGB")
                self.sprites = sprites
            except FileNotFoundError as e:
                print(f"Error loading sprite image: {e}")
                self.sprite_sheet = None
                self.sprites = []
        
        self.current_sprite_index = 0

    def on_event(self, event: str, **kwargs) -> None:
        if event.lower() == "show_sprite":
            index = kwargs.get("index")
            if index is not None and 0 <= int(index) < len(self.sprites):
                self.current_sprite_index = int(index)

    def render_into(self, t: float, pixel_buf: bytearray):
        if not self.sprite_sheet or not self.sprites or self.current_sprite_index >= len(self.sprites):
            return

        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        if self.clear_on_frame:
            frame[:, :] = (0, 0, 0)  # Clear to black

        sprite_coords = self.sprites[self.current_sprite_index]
        x, y, w, h = sprite_coords
        
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
            frame[dest_y_start:dest_y_end, dest_x_start:dest_x_end] = \
                sprite_array[src_y_start:src_y_end, src_x_start:src_x_end]
