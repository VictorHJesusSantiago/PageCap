"""
Font converter: ttf ↔ otf ↔ woff ↔ woff2 ↔ eot
Backend: fonttools (pip install fonttools brotli zopfli)
"""
from __future__ import annotations

from pathlib import Path


async def convert_font(src: Path, target_ext: str) -> Path:
    """Convert font file to target_ext. Returns converted file path."""
    try:
        from fontTools.ttLib import TTFont
        from fontTools.ttLib.woff2 import compress as woff2_compress, decompress as woff2_decompress
    except ImportError:
        raise RuntimeError(
            "fonttools não instalado. Execute: pip install fonttools brotli"
        )

    src_ext = src.suffix.lower()
    dest = src.with_suffix(target_ext)

    if src_ext == ".woff2":
        # Decompress WOFF2 → TTF first
        tmp_ttf = src.with_suffix(".tmp.ttf")
        with open(src, "rb") as f_in, open(tmp_ttf, "wb") as f_out:
            woff2_decompress(f_in, f_out)
        src = tmp_ttf
        src_ext = ".ttf"

    font = TTFont(str(src))

    if target_ext == ".woff2":
        with open(dest, "wb") as f_out:
            woff2_compress(font, f_out)
    elif target_ext == ".woff":
        font.flavor = "woff"
        font.save(str(dest))
    elif target_ext in (".ttf", ".otf"):
        font.flavor = None
        font.save(str(dest))
    elif target_ext == ".eot":
        # EOT requires a dedicated tool; use ttf2eot if available
        import shutil, asyncio
        if not shutil.which("ttf2eot"):
            raise RuntimeError("ttf2eot não encontrado. Instale-o para gerar EOT.")
        proc = await asyncio.create_subprocess_exec(
            "ttf2eot", str(src), str(dest),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
    else:
        raise ValueError(f"Conversão de fonte para {target_ext} não suportada")

    # Clean up temp file if created
    tmp = src.parent / (src.stem.replace(".tmp", "") + ".tmp.ttf")
    if tmp.exists():
        tmp.unlink(missing_ok=True)

    return dest
