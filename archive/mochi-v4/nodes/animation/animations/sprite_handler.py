# animations/sprite_handler.py

"""Sprite Handler — sprite-sheet rendering (static + animated).

TWO MODES depending on which kwargs are present:

A. STATIC (legacy, mscript-driven)
   kwargs:
     - asset_path      sheet image path
     - SRC = "x,y,w,h" pixel rect to crop

B. ANIMATED (new in 4/6 — sidecar / catalog driven)
   kwargs:
     - asset_path      sheet image path
     - frame_size      [w, h] of each cell
     - frame_count     total cells (animation length)
     - grid            [cols, rows] (derived from sheet size if omitted)
     - frame_rate_ms   ms per frame (default 100)
     - start_frame     first cell in the animation loop (default 0)
     - end_frame       last cell (default frame_count - 1)
     - named_frame     name of a specific slot — overrides animation;
                       renders one static cell
     - named_frames    {name: cell_index, ...} lookup table

Picks the right mode automatically: SRC present → static, otherwise
grid kwargs → animated.

Per docs/ASSET_PROPERTIES.md the sidecar's ``type_props`` block
maps directly onto the animated kwargs above:

    type_props:
      frame_size: [64, 64]
      frame_count: 12
      grid: [4, 3]
      frame_rate_ms: 100
      named_frames:
        idle: 0
        walk_1: 1
"""

import os
from typing import Tuple
import numpy as np
from plugin_core.mochi_animations import Animation
from PIL import Image

from .decoders import resize_frame


class SpriteHandler(Animation):
    name = "SPRITE"

    def __init__(self, w: int, h: int):
        super().__init__(w, h)
        self.sprite_sheet: Image.Image | None = None

        # Static (SRC) mode
        self.sprite_coords: Tuple[int, int, int, int] | None = None

        # Animated (grid) mode
        self._frame_w: int = 0
        self._frame_h: int = 0
        self._frame_count: int = 0
        self._cols: int = 1
        self._rows: int = 1
        self._frame_rate_ms: int = 100
        self._start_frame: int = 0
        self._end_frame: int = 0
        self._fixed_index: int | None = None   # set by named_frame
        self._framing: str = "fit"             # fit | fill | stretch
        self._t0: float | None = None          # activation anchor (first render t)

    def on_enter(self, **kwargs) -> None:
        super().on_enter(**kwargs)

        # Restart the animation clock on every activation so playback
        # begins at start_frame (anchored on first render, see
        # _current_index_for_time).
        self._t0 = None

        resolve_dir = kwargs.get("resolve_dir")
        asset_path = kwargs.get("asset_path")

        # How a cell is mapped onto the display when sizes differ.
        # Mirrors the decoded-media handlers ("framing" sidecar prop,
        # "fit" mscript kwarg).
        self._framing = str(
            kwargs.get("framing") or kwargs.get("fit") or "fit"
        )

        # Load the sheet first — both modes need it
        if asset_path:
            try:
                if not os.path.isabs(asset_path) and resolve_dir:
                    asset_path = os.path.join(resolve_dir, asset_path)
                self.sprite_sheet = Image.open(asset_path).convert("RGB")
            except FileNotFoundError as e:
                print(f"Error loading sprite image: {e}")
                self.sprite_sheet = None

        # ── STATIC (legacy) — SRC=x,y,w,h overrides everything ────
        src_rect_str = kwargs.get("SRC")
        if src_rect_str:
            try:
                coords = [int(c.strip()) for c in src_rect_str.split(",")]
                if len(coords) == 4:
                    self.sprite_coords = tuple(coords)
                    return
                print(f"Warning: Invalid SRC format: {src_rect_str}")
            except (ValueError, AttributeError):
                print(f"Warning: Could not parse SRC rect: {src_rect_str}")
            # Malformed SRC — fall through so any grid kwargs in the
            # same call still apply.

        # ── ANIMATED (grid-driven) ────────────────────────────────
        frame_size = kwargs.get("frame_size")
        if not frame_size or not self.sprite_sheet:
            return  # neither mode applicable — render_into will no-op

        try:
            self._frame_w = int(frame_size[0])
            self._frame_h = int(frame_size[1])
        except (TypeError, IndexError, ValueError):
            return

        def _int_kwarg(key: str, default: int) -> int:
            raw = kwargs.get(key, default)
            try:
                return int(raw)
            except (TypeError, ValueError):
                print(f"Warning: invalid {key} value {raw!r}; using {default}")
                return default

        self._frame_count = _int_kwarg("frame_count", 0)
        self._frame_rate_ms = _int_kwarg("frame_rate_ms", 100)
        self._start_frame = _int_kwarg("start_frame", 0)
        self._end_frame = _int_kwarg("end_frame", max(0, self._frame_count - 1))

        # Derive grid (cols × rows) from sheet size when omitted
        sheet_w, sheet_h = self.sprite_sheet.size
        derived_cols = max(1, sheet_w // max(1, self._frame_w))
        derived_rows = max(1, sheet_h // max(1, self._frame_h))
        grid = kwargs.get("grid")
        explicit_grid = False
        if grid and len(grid) == 2:
            try:
                self._cols = max(1, int(grid[0]))
                self._rows = max(1, int(grid[1]))
                explicit_grid = True
            except (TypeError, ValueError):
                print(f"Warning: invalid grid value {grid!r}; deriving from sheet size")
        if not explicit_grid:
            self._cols = derived_cols
            self._rows = derived_rows
        elif (self._cols * self._frame_w > sheet_w
              or self._rows * self._frame_h > sheet_h):
            # An oversized explicit grid would crop past the sheet edge
            # and silently render black zero-padded cells.
            print(
                f"Warning: grid [{self._cols}, {self._rows}] exceeds sheet "
                f"size {sheet_w}x{sheet_h}; clamping to "
                f"[{min(self._cols, derived_cols)}, {min(self._rows, derived_rows)}]"
            )
            self._cols = min(self._cols, derived_cols)
            self._rows = min(self._rows, derived_rows)

        # If frame_count wasn't given, infer from grid
        if self._frame_count <= 0:
            self._frame_count = self._cols * self._rows
            self._end_frame = self._frame_count - 1

        # Clamp the [start_frame, end_frame] window to the cells that
        # actually exist, so loops never replay wrapped cells or
        # silently freeze.
        max_index = max(0, self._frame_count - 1)
        if self._end_frame > max_index:
            print(
                f"Warning: end_frame {self._end_frame} exceeds last frame "
                f"{max_index}; clamping"
            )
            self._end_frame = max_index
        if self._start_frame > self._end_frame:
            print(
                f"Warning: start_frame {self._start_frame} > end_frame "
                f"{self._end_frame}; clamping"
            )
            self._start_frame = self._end_frame

        # named_frame: pin the renderer to one specific cell
        named_frame = kwargs.get("named_frame")
        named_frames = kwargs.get("named_frames") or {}
        if named_frame and isinstance(named_frames, dict):
            idx = named_frames.get(named_frame)
            if idx is not None:
                try:
                    idx = int(idx)
                except (TypeError, ValueError):
                    print(
                        f"Warning: named_frame '{named_frame}' has "
                        f"non-integer index {named_frames.get(named_frame)!r}"
                    )
                    idx = None
            if idx is not None:
                if 0 <= idx < self._frame_count:
                    self._fixed_index = idx
                else:
                    print(
                        f"Warning: named_frame '{named_frame}' index {idx} "
                        f"out of range (frame_count={self._frame_count})"
                    )

    # ──────────────────────────────────────────────────────────────

    def _cell_at_index(self, index: int) -> Tuple[int, int, int, int]:
        """Return the (x, y, w, h) crop rect for cell ``index`` in
        the grid.  Index wraps within the grid."""
        n = max(1, self._cols * self._rows)
        index = index % n
        col = index % self._cols
        row = index // self._cols
        return (
            col * self._frame_w,
            row * self._frame_h,
            self._frame_w,
            self._frame_h,
        )

    def _current_index_for_time(self, t: float) -> int:
        """Wrap elapsed-since-activation into the [start_frame,
        end_frame] loop.  Anchored on the first render so every
        activation starts at start_frame (mirrors media_base.py)."""
        if self._t0 is None:
            self._t0 = t
        if self._frame_rate_ms <= 0 or self._frame_count <= 0:
            return self._start_frame
        loop_len = max(1, (self._end_frame - self._start_frame + 1))
        elapsed = max(0.0, t - self._t0)
        elapsed_frames = int((elapsed * 1000.0) / self._frame_rate_ms)
        return self._start_frame + (elapsed_frames % loop_len)

    # ──────────────────────────────────────────────────────────────

    def render_into(self, t: float, pixel_buf: bytearray):
        if not self.sprite_sheet:
            return

        # Pick the cell rect for THIS frame
        if self.sprite_coords:
            x, y, w, h = self.sprite_coords           # static SRC mode
        elif self._fixed_index is not None:
            x, y, w, h = self._cell_at_index(self._fixed_index)   # named slot
        elif self._frame_w and self._frame_h:
            idx = self._current_index_for_time(t)
            x, y, w, h = self._cell_at_index(idx)     # animated mode
        else:
            return

        frame = np.frombuffer(pixel_buf, dtype=np.uint8).reshape(
            (self.h, self.w, 3)
        )
        if self.clear_on_frame:
            frame[:, :] = (0, 0, 0)

        sprite_image = self.sprite_sheet.crop((x, y, x + w, y + h))
        # Honor the framing prop like the decoded-media handlers do:
        # scale the cell to the display via fit / fill / stretch.
        # Fast path: same size → direct blit below, no resampling.
        if sprite_image.size != (self.w, self.h):
            sprite_image = resize_frame(
                sprite_image, (self.w, self.h), self._framing, (0, 0, 0)
            )
        sprite_array = np.array(sprite_image)
        img_h, img_w, _ = sprite_array.shape

        # Center the sprite on the display
        start_x = (self.w - img_w) // 2
        start_y = (self.h - img_h) // 2

        dest_y_start = max(0, start_y)
        dest_y_end = min(self.h, start_y + img_h)
        dest_x_start = max(0, start_x)
        dest_x_end = min(self.w, start_x + img_w)

        src_y_start = max(0, -start_y)
        src_y_end = src_y_start + (dest_y_end - dest_y_start)
        src_x_start = max(0, -start_x)
        src_x_end = src_x_start + (dest_x_end - dest_x_start)

        if dest_y_start < dest_y_end and dest_x_start < dest_x_end:
            safe_src_y_end = min(sprite_array.shape[0], src_y_end)
            safe_src_x_end = min(sprite_array.shape[1], src_x_end)
            frame[
                dest_y_start:dest_y_end,
                dest_x_start:dest_x_end,
            ] = sprite_array[
                src_y_start:safe_src_y_end,
                src_x_start:safe_src_x_end,
            ]
