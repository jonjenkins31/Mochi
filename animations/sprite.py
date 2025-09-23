
import json
from typing import List, Tuple
import numpy as np
from core.mochi_animations import Animation
from PIL import Image

class Sprite(Animation):
    name = "sprite"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.sprite_sheet = None
        self.sprites: List[Tuple[int, int, int, int]] = []
        self.current_sprite_index = 0

    def _load_config(self, config_path: str):
        """Loads the sprite animation configuration from a JSON file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            image_path = config.get("image_path")
            if image_path:
                self.sprite_sheet = Image.open(image_path).convert("RGB")
            
            self.sprites = config.get("sprites", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading sprite config: {e}")
            self.sprite_sheet = None
            self.sprites = []

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        
        config_path = kwargs.get("config_path")
        image_path = kwargs.get("image_path")
        sprites = kwargs.get("sprites")

        if image_path and sprites is not None:
            try:
                self.sprite_sheet = Image.open(image_path).convert("RGB")
                self.sprites = sprites
            except FileNotFoundError as e:
                print(f"Error loading sprite image: {e}")
                self.sprite_sheet = None
                self.sprites = []
        elif config_path:
            self._load_config(config_path)
        
        # Default to showing the first sprite
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

        # Center the sprite
        start_x = (self.w - w) // 2
        start_y = (self.h - h) // 2

        # Clamp to frame buffer dimensions
        img_h, img_w, _ = sprite_array.shape
        for i in range(img_h):
            for j in range(img_w):
                if 0 <= start_y + i < self.h and 0 <= start_x + j < self.w:
                    frame[start_y + i, start_x + j] = sprite_array[i, j]
