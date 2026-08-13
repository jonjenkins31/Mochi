"""Vectorised Conway's Game of Life procedural scene.

The original file was a terminal demo with a blocking ``while True`` and no
Mochi ``Animation`` subclass, so neither the v3 loader nor JaegerAnimation
could instantiate it.  This version preserves its Conway seed and random
restart behavior behind the normal procedural-animation contract.
"""

from __future__ import annotations

import numpy as np

from plugin_core.mochi_animations import Animation


class GameOfLife2(Animation):
    name = "game_of_life_2"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.fg = (80, 255, 140)
        self.bg = (0, 0, 0)
        self.step_s = 0.08
        self._last_step = -1.0
        self._rng = np.random.default_rng()
        self._cells = np.zeros((h, w), dtype=bool)
        self._seed_conway()

    def _seed_conway(self) -> None:
        pattern = (
            "  +++   ",
            "  + +   ",
            "  + +   ",
            "   +    ",
            "+ +++   ",
            " + + +  ",
            "   +  + ",
            "  + +   ",
            "  + +   ",
        )
        self._cells.fill(False)
        top = max(0, (self.h - len(pattern)) // 2)
        left = max(0, (self.w - len(pattern[0])) // 2)
        for row, line in enumerate(pattern):
            if top + row >= self.h:
                break
            for column, value in enumerate(line):
                if value == "+" and left + column < self.w:
                    self._cells[top + row, left + column] = True

    def on_enter(self, **kwargs) -> None:
        fg = kwargs.get("FG", kwargs.get("fg", self.fg))
        bg = kwargs.get("BG", kwargs.get("bg", self.bg))
        if isinstance(fg, (list, tuple)) and len(fg) >= 3:
            self.fg = tuple(int(value) for value in fg[:3])
        if isinstance(bg, (list, tuple)) and len(bg) >= 3:
            self.bg = tuple(int(value) for value in bg[:3])
        self.step_s = max(0.01, float(kwargs.get("step_s", self.step_s)))
        seed = kwargs.get("seed")
        if seed is not None:
            self._rng = np.random.default_rng(int(seed))

    def _advance(self) -> None:
        cells = self._cells
        neighbors = sum(
            np.roll(np.roll(cells, dy, axis=0), dx, axis=1)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if dx or dy
        )
        self._cells = (neighbors == 3) | (cells & (neighbors == 2))
        if not self._cells.any():
            self._cells = self._rng.random((self.h, self.w)) < 0.33

    def render_into(self, t: float, pixel_buf) -> None:
        target_step = int(max(0.0, t) / self.step_s)
        if self._last_step < 0:
            self._last_step = target_step
        while self._last_step < target_step:
            self._advance()
            self._last_step += 1

        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape(
            (self.h, self.w, 3))
        frame[:] = self.bg
        frame[self._cells] = self.fg


__all__ = ["GameOfLife2"]
