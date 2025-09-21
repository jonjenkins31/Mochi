
import json
import time
from typing import List, Tuple
import numpy as np
from .base import Animation
from PIL import Image

class Sprite(Animation):
    name = "sprite"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.sprite_sheet = None
        self.sprites: List[Tuple[int, int, int, int]] = []
        self.timings: List[float] = []
        self.current_sprite_index = 0
        self.last_frame_time = 0

    def _load_config(self, config_path: str):
        """Loads the sprite animation configuration from a JSON file."""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            image_path = config.get("image_path")
            if image_path:
                self.sprite_sheet = Image.open(image_path).convert("RGB")
            
            self.sprites = config.get("sprites", [])
            self.timings = config.get("timings", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading sprite config: {e}")
            self.sprite_sheet = None
            self.sprites = []
            self.timings = []

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)
        
        config_path = kwargs.get("config_path")
        if config_path:
            self._load_config(config_path)
        
        self.last_frame_time = time.time()
        self.current_sprite_index = 0

    def render_into(self, t: float, pixel_buf: bytearray):
        if not self.sprite_sheet or not self.sprites:
            return

        now = time.time()
        delta_time = now - self.last_frame_time

        if self.timings and len(self.timings) > self.current_sprite_index and delta_time >= self.timings[self.current_sprite_index]:
            self.current_sprite_index = (self.current_sprite_index + 1) % len(self.sprites)
            self.last_frame_time = now

        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape((self.h, self.w, 3))
        if self.clear_on_frame:
            frame[:, :] = (0, 0, 0)  # Clear to black

        if len(self.sprites) > self.current_sprite_index:
            sprite_coords = self.sprites[self.current_sprite_index]
            x, y, w, h = sprite_coords
            
            sprite_image = self.sprite_sheet.crop((x, y, x + w, y + h))
            sprite_array = np.array(sprite_image)

            # Center the sprite
            start_x = (self.w - w) // 2
            start_y = (self.h - h) // 2

            for i in range(h):
                for j in range(w):
                    if 0 <= start_y + i < self.h and 0 <= start_x + j < self.w:
                        frame[start_y + i, start_x + j] = sprite_array[i, j]
