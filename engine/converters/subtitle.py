"""
Subtitle converter: srt ↔ vtt ↔ ass/ssa ↔ ttml ↔ lrc
Pure Python — no external tools required.
"""
from __future__ import annotations

import re
from pathlib import Path


async def convert_subtitle(src: Path, target_ext: str) -> Path:
    """Convert subtitle file. Returns path to converted file."""
    src_ext = src.suffix.lower()
    dest = src.with_suffix(target_ext)

    try:
        import pysubs2
        subs = pysubs2.load(str(src))
        _pysubs2_save(subs, dest, target_ext)
        return dest
    except ImportError:
        pass  # fallback below

    # Manual SRT ↔ VTT fallback (no dependency)
    text = src.read_text(encoding="utf-8", errors="replace")

    if src_ext == ".srt" and target_ext == ".vtt":
        dest.write_text(_srt_to_vtt(text), encoding="utf-8")
    elif src_ext == ".vtt" and target_ext == ".srt":
        dest.write_text(_vtt_to_srt(text), encoding="utf-8")
    else:
        raise RuntimeError(
            f"Conversão {src_ext}→{target_ext} requer: pip install pysubs2"
        )

    return dest


def _pysubs2_save(subs, dest: Path, target_ext: str):
    fmt_map = {
        ".srt": "srt", ".vtt": "vtt", ".ass": "ass", ".ssa": "ass",
        ".ttml": "ttml", ".sbv": "sbv",
    }
    fmt = fmt_map.get(target_ext)
    if not fmt:
        raise ValueError(f"Formato de legenda não suportado: {target_ext}")
    subs.save(str(dest), format_=fmt)


def _srt_to_vtt(srt: str) -> str:
    vtt = "WEBVTT\n\n"
    vtt += re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt)
    return vtt


def _vtt_to_srt(vtt: str) -> str:
    lines = vtt.lstrip("WEBVTT").strip().splitlines()
    srt_lines = []
    counter = 1
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Detect timestamp line
        if "-->" in line:
            # Add counter
            srt_lines.append(str(counter))
            counter += 1
            # Convert timestamps
            srt_lines.append(re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", line))
            i += 1
            # Collect text lines
            while i < len(lines) and lines[i].strip():
                srt_lines.append(lines[i].rstrip())
                i += 1
            srt_lines.append("")
        else:
            i += 1
    return "\n".join(srt_lines)
