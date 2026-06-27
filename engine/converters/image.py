"""
Image converter.

Backends (in priority order):
  1. Pillow + pillow-heif + pillow-avif  → raster conversions (jpg/png/webp/avif/bmp/tiff/gif/heic/ico)
  2. cairosvg                            → svg → png/pdf/ps
  3. ImageMagick (magick / convert CLI)  → fallback for exotic formats (psd, xcf, raw, eps, wmf)
  4. ffmpeg                              → gif → mp4/webm
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

_PIL_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif",
             ".ico", ".ppm", ".pgm", ".pbm", ".xbm"}
_AVIF_EXTS = {".avif"}
_HEIC_EXTS = {".heic", ".heif"}
_SVG_EXTS  = {".svg"}
_RAW_EXTS  = {".raw", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2"}
_PS_EXTS   = {".eps", ".ai", ".ps", ".psd", ".xcf", ".wmf", ".emf", ".sketch"}

# Pillow format names
_PIL_FMT: dict[str, str] = {
    ".jpg": "JPEG", ".jpeg": "JPEG",
    ".png": "PNG", ".gif": "GIF", ".bmp": "BMP",
    ".webp": "WEBP", ".tiff": "TIFF", ".tif": "TIFF",
    ".ico": "ICO", ".ppm": "PPM",
}


def _has_magick() -> bool:
    return shutil.which("magick") is not None or shutil.which("convert") is not None


def _magick_cmd() -> str:
    return "magick" if shutil.which("magick") else "convert"


async def convert_image(src: Path, target_ext: str) -> Path:
    """
    Convert image at `src` to `target_ext`.
    Returns path of converted file (same directory as src).
    """
    src_ext = src.suffix.lower()
    dest = src.with_suffix(target_ext)
    target_ext = target_ext.lower()

    # ── GIF → video ───────────────────────────────────────────────────────────
    if src_ext == ".gif" and target_ext in (".mp4", ".webm"):
        return await _gif_to_video(src, dest, target_ext)

    # ── SVG → raster / pdf ────────────────────────────────────────────────────
    if src_ext == ".svg":
        return await _svg_convert(src, dest, target_ext)

    # ── HEIC/HEIF → any ───────────────────────────────────────────────────────
    if src_ext in _HEIC_EXTS:
        return await _heic_convert(src, dest, target_ext)

    # ── AVIF → any ────────────────────────────────────────────────────────────
    if src_ext in _AVIF_EXTS or target_ext in _AVIF_EXTS:
        return await _avif_convert(src, dest, target_ext)

    # ── RAW → any ─────────────────────────────────────────────────────────────
    if src_ext in _RAW_EXTS:
        return await _raw_convert(src, dest, target_ext)

    # ── Exotic (PSD, XCF, EPS, WMF) → via ImageMagick ────────────────────────
    if src_ext in _PS_EXTS:
        return await _magick_convert(src, dest)

    # ── Standard raster via Pillow ────────────────────────────────────────────
    if src_ext in _PIL_EXTS or target_ext in _PIL_EXTS:
        return await _pillow_convert(src, dest, target_ext)

    # Final fallback: ImageMagick
    return await _magick_convert(src, dest)


async def _pillow_convert(src: Path, dest: Path, target_ext: str) -> Path:
    from PIL import Image
    img = Image.open(src)
    if target_ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    if target_ext == ".ico":
        img.save(str(dest), format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    else:
        fmt = _PIL_FMT.get(target_ext, target_ext.lstrip(".").upper())
        img.save(str(dest), format=fmt)
    return dest


async def _svg_convert(src: Path, dest: Path, target_ext: str) -> Path:
    try:
        import cairosvg
        if target_ext == ".png":
            cairosvg.svg2png(url=str(src), write_to=str(dest))
        elif target_ext == ".pdf":
            cairosvg.svg2pdf(url=str(src), write_to=str(dest))
        elif target_ext in (".jpg", ".jpeg"):
            tmp_png = src.with_suffix(".tmp.png")
            cairosvg.svg2png(url=str(src), write_to=str(tmp_png))
            return await _pillow_convert(tmp_png, dest, target_ext)
        else:
            return await _magick_convert(src, dest)
        return dest
    except ImportError:
        return await _magick_convert(src, dest)


async def _heic_convert(src: Path, dest: Path, target_ext: str) -> Path:
    try:
        from PIL import Image
        import pillow_heif
        pillow_heif.register_heif_opener()
        img = Image.open(src)
        return await _pillow_convert_img(img, dest, target_ext)
    except ImportError:
        return await _magick_convert(src, dest)


async def _pillow_convert_img(img, dest: Path, target_ext: str) -> Path:
    from PIL import Image
    if target_ext in (".jpg", ".jpeg") and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    fmt = _PIL_FMT.get(target_ext, target_ext.lstrip(".").upper())
    img.save(str(dest), format=fmt)
    return dest


async def _avif_convert(src: Path, dest: Path, target_ext: str) -> Path:
    try:
        import pillow_avif
        from PIL import Image
        img = Image.open(src)
        return await _pillow_convert_img(img, dest, target_ext)
    except ImportError:
        return await _magick_convert(src, dest)


async def _raw_convert(src: Path, dest: Path, target_ext: str) -> Path:
    """Convert camera RAW using rawpy + Pillow."""
    try:
        import rawpy
        import numpy as np
        from PIL import Image
        with rawpy.imread(str(src)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
        img = Image.fromarray(rgb)
        return await _pillow_convert_img(img, dest, target_ext)
    except ImportError:
        return await _magick_convert(src, dest)


async def _gif_to_video(src: Path, dest: Path, target_ext: str) -> Path:
    """Convert animated GIF to MP4 or WebM using ffmpeg."""
    codec = "libvpx-vp9" if target_ext == ".webm" else "libx264"
    extra = ["-b:v", "0", "-crf", "30"] if target_ext == ".webm" else ["-crf", "22", "-movflags", "+faststart"]
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
           "-c:v", codec, *extra, str(dest)]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    if dest.exists():
        return dest
    raise RuntimeError("ffmpeg falhou ao converter GIF → vídeo")


async def _magick_convert(src: Path, dest: Path) -> Path:
    """Fallback conversion using ImageMagick."""
    if not _has_magick():
        raise RuntimeError(
            "ImageMagick não encontrado. Instale em https://imagemagick.org/script/download.php"
        )
    cmd_name = _magick_cmd()
    cmd = [cmd_name, str(src), str(dest)]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ImageMagick falhou: {stderr.decode()[:300]}")
    return dest
