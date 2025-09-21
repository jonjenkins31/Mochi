# core/media.py
from __future__ import annotations
from typing import Optional, List, Tuple
from PIL import Image
import logging

# --- Logging Setup ---
logger = logging.getLogger(__name__)

class MediaFrames:
    """A container for decoded media frames and their timings."""
    def __init__(self, frames: List[Image.Image], durations_ms: List[int]):
        self.frames: List[Image.Image] = frames
        self.durations_ms: List[int] = durations_ms
        self.total_duration: int = sum(d if d > 0 else 100 for d in self.durations_ms)

    @property
    def frame_count(self) -> int:
        return len(self.frames)

def decode_image(path: str, target_size: Tuple[int, int], fit_mode: str = 'fit', letterbox_color: Tuple[int, int, int] = (0, 0, 0)) -> Optional[MediaFrames]:
    """
    Opens a media file (static image, GIF, APNG) and decodes it into a standardized format.

    Args:
        path: Path to the media file.
        target_size: The (width, height) of the output display.
        fit_mode: How to resize the image ('fit', 'fill', 'stretch').
        letterbox_color: RGB color for the letterbox background if using 'fit' mode.

    Returns:
        A MediaFrames object containing the processed frames, or None if decoding fails.
    """
    try:
        img = Image.open(path)
    except Exception as e:
        logger.error(f"Failed to open image file: {path} ({e})")
        return None

    frames = []
    durations = []
    w_target, h_target = target_size

    try:
        for i in range(img.n_frames):
            img.seek(i)
            frame = img.copy()

            # --- Convert to standard RGB ---
            if frame.mode != 'RGB':
                frame = frame.convert('RGB')

            # --- Resize and Fit ---
            if frame.size != target_size:
                # Use NEAREST filter for sharp, pixel-perfect scaling of low-res assets
                resample_filter = Image.NEAREST

                if fit_mode == 'stretch':
                    frame = frame.resize(target_size, resample=resample_filter)
                else: # 'fit' (letterbox) or 'fill' (crop)
                    img_ratio = frame.width / frame.height
                    target_ratio = w_target / h_target
                    
                    if (fit_mode == 'fit' and img_ratio > target_ratio) or \
                       (fit_mode == 'fill' and img_ratio < target_ratio):
                        # Fit to width
                        scale_h = int(w_target / img_ratio)
                        scaled_img = frame.resize((w_target, scale_h), resample=resample_filter)
                    else:
                        # Fit to height
                        scale_w = int(h_target * img_ratio)
                        scaled_img = frame.resize((scale_w, h_target), resample=resample_filter)

                    # Create background and paste the scaled image
                    new_frame = Image.new('RGB', target_size, letterbox_color)
                    paste_x = (w_target - scaled_img.width) // 2
                    paste_y = (h_target - scaled_img.height) // 2
                    new_frame.paste(scaled_img, (paste_x, paste_y))
                    frame = new_frame

            frames.append(frame)
            durations.append(img.info.get('duration', 100))

    except EOFError:
        pass
    except Exception as e:
        logger.error(f"Error processing frames for {path}: {e}")
        return None

    if not frames:
        logger.warning(f"No frames could be decoded from {path}")
        return None

    logger.info(f"Successfully decoded {len(frames)} frames from {path}")
    return MediaFrames(frames, durations)
