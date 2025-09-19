# utils/media.py
from __future__ import annotations
from typing import List, Tuple, Optional, Union
from dataclasses import dataclass
from PIL import Image, ImageOps
import io
import os

try:
    import cairosvg  # optional for SVG
    _HAS_CAIROSVG = True
except Exception:
    _HAS_CAIROSVG = False

@dataclass
class MediaFrames:
    frames: List[Image.Image]        # RGB frames
    durations_ms: List[int]          # per-frame durations (ms), same length as frames

def _ensure_rgb(im: Image.Image) -> Image.Image:
    if im.mode == "RGB":
        return im
    if im.mode in ("RGBA", "LA"):
        return im.convert("RGBA").convert("RGB")
    return im.convert("RGB")

def _resize(im: Image.Image, target: Optional[Tuple[int,int]], fit_mode: str, letterbox_color=(0,0,0)) -> Image.Image:
    """
    fit_mode: 'fit' (letterbox to fit within), 'fill' (cover + center-crop), or 'stretch'
    """
    if not target:
        return im
    tw, th = target
    if fit_mode == "stretch":
        return im.resize((tw, th), Image.NEAREST)
    # keep aspect
    src_w, src_h = im.size
    if fit_mode == "fit":
        out = Image.new("RGB", (tw, th), letterbox_color)
        im2 = ImageOps.contain(im, (tw, th), method=Image.NEAREST)
        x = (tw - im2.width)//2
        y = (th - im2.height)//2
        out.paste(im2, (x, y))
        return out
    elif fit_mode == "fill":
        # scale to cover then center-crop
        scale = max(tw/src_w, th/src_h) if src_w and src_h else 1.0
        new_w = max(1, int(src_w*scale))
        new_h = max(1, int(src_h*scale))
        im2 = im.resize((new_w, new_h), Image.NEAREST)
        x = (new_w - tw)//2
        y = (new_h - th)//2
        return im2.crop((x, y, x+tw, y+th))
    return im

def _decode_svg(data: bytes, css_px_size: Optional[Tuple[int,int]]) -> Image.Image:
    if not _HAS_CAIROSVG:
        raise RuntimeError("SVG support requires 'cairosvg' (pip install cairosvg)")
    png_bytes = cairosvg.svg2png(bytestring=data,
                                 output_width=css_px_size[0] if css_px_size else None,
                                 output_height=css_px_size[1] if css_px_size else None)
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")

def _is_svg(path_or_bytes: Union[str, bytes]) -> bool:
    if isinstance(path_or_bytes, str):
        return os.path.splitext(path_or_bytes)[1].lower() == ".svg"
    # crude sniff
    head = path_or_bytes[:200].lstrip() if isinstance(path_or_bytes, (bytes, bytearray)) else b""
    return head.startswith(b"<svg") or b"<svg" in head

def decode_image(
    src: Union[str, bytes, bytearray],
    target_size: Optional[Tuple[int,int]] = None,
    fit_mode: str = "fit",              # 'fit' | 'fill' | 'stretch'
    letterbox_color=(0,0,0),
) -> MediaFrames:
    """
    Generic image loader → RGB frames (+ durations). Handles still images and GIF/APNG.
    """
    if isinstance(src, (bytes, bytearray)):
        buf = io.BytesIO(src)
        is_svg = _is_svg(src)
    else:
        is_svg = src.lower().endswith(".svg")
        buf = None

    if is_svg:
        if isinstance(src, (bytes, bytearray)):
            im = _decode_svg(bytes(src), css_px_size=target_size)
        else:
            with open(src, "rb") as f:
                im = _decode_svg(f.read(), css_px_size=target_size)
        im = _ensure_rgb(im)
        im = _resize(im, target_size, fit_mode, letterbox_color)
        return MediaFrames([im], [0])

    # Raster formats (Pillow)
    im = Image.open(buf if buf is not None else src)
    # animated?
    frames: List[Image.Image] = []
    durations: List[int] = []
    try:
        im.seek(0)
    except EOFError:
        pass
    idx = 0
    while True:
        frm = _ensure_rgb(im.copy())
        frm = _resize(frm, target_size, fit_mode, letterbox_color)
        dur = im.info.get("duration", 0)  # GIF/APNG ms
        frames.append(frm)
        durations.append(int(dur))
        idx += 1
        try:
            im.seek(idx)
        except EOFError:
            break
    if not frames:
        frm = _ensure_rgb(im)
        frm = _resize(frm, target_size, fit_mode, letterbox_color)
        frames = [frm]; durations = [0]
    return MediaFrames(frames, durations)

# --- 1-bit packed bitmap (row-major, MSB-first), like Arduino PROGMEM ---

def decode_packed_1bit(
    bitmap_bytes: bytes,
    width: int,
    height: int,
    on=(255,255,255),
    off=(0,0,0),
    target_size: Optional[Tuple[int,int]] = None,
    fit_mode: str = "fit",
    letterbox_color=(0,0,0),
) -> MediaFrames:
    bytes_per_row = (width + 7) // 8
    im = Image.new("RGB", (width, height), off)
    px = im.load()
    for y in range(height):
        row_off = y * bytes_per_row
        for x in range(width):
            bi = row_off + (x // 8)
            bit = 7 - (x % 8)
            onbit = ((bitmap_bytes[bi] >> bit) & 1) != 0
            px[x, y] = on if onbit else off
    im = _resize(im, target_size, fit_mode, letterbox_color)
    return MediaFrames([im], [0])