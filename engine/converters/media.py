"""
Audio/Video converter via ffmpeg.
Handles: mp4, mkv, avi, mov, wmv, flv, webm, ogv, 3gp, ts, vob, rm
         mp3, wav, ogg, flac, aac, m4a, wma, opus, aiff
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".opus", ".aiff", ".aif"}
_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".ogv", ".3gp", ".ts", ".m2ts", ".vob", ".rm", ".rmvb"}

# ffmpeg codec recommendations per output format
_VCODEC: dict[str, str] = {
    ".mp4": "libx264", ".mkv": "libx264", ".avi": "libxvid",
    ".mov": "libx264", ".wmv": "wmv2", ".webm": "libvpx-vp9",
    ".ogv": "libtheora", ".3gp": "libx264", ".flv": "flv",
}
_ACODEC: dict[str, str] = {
    ".mp3": "libmp3lame", ".wav": "pcm_s16le", ".ogg": "libvorbis",
    ".flac": "flac", ".aac": "aac", ".m4a": "aac",
    ".wma": "wmav2", ".opus": "libopus", ".aiff": "pcm_s16be", ".aif": "pcm_s16be",
}


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


async def convert_media(src: Path, target_ext: str, quality: str = "medium") -> Path:
    """
    Convert audio or video file to target_ext.
    quality: "low" | "medium" | "high" | "lossless"
    Returns path to converted file.
    """
    if not _has_ffmpeg():
        raise RuntimeError(
            "ffmpeg não encontrado no PATH. Instale em https://ffmpeg.org/download.html"
        )

    src_ext = src.suffix.lower()
    dest = src.with_suffix(target_ext)
    is_audio_target = target_ext in _AUDIO_EXTS

    cmd = ["ffmpeg", "-y", "-i", str(src)]

    if is_audio_target:
        # Audio-only extraction / conversion
        acodec = _ACODEC.get(target_ext, "copy")
        cmd += ["-vn", "-c:a", acodec]
        if target_ext == ".mp3":
            q = {"low": "9", "medium": "4", "high": "2", "lossless": "0"}.get(quality, "4")
            cmd += ["-q:a", q]
        elif target_ext == ".flac":
            cmd += ["-compression_level", "8"]
        elif target_ext in (".aac", ".m4a"):
            br = {"low": "96k", "medium": "192k", "high": "256k", "lossless": "320k"}.get(quality, "192k")
            cmd += ["-b:a", br]
        elif target_ext == ".opus":
            br = {"low": "64k", "medium": "128k", "high": "192k", "lossless": "256k"}.get(quality, "128k")
            cmd += ["-b:a", br]
        elif target_ext == ".ogg":
            q = {"low": "3", "medium": "5", "high": "7", "lossless": "10"}.get(quality, "5")
            cmd += ["-q:a", q]
    else:
        # Video conversion
        vcodec = _VCODEC.get(target_ext, "libx264")
        cmd += ["-c:v", vcodec]

        if target_ext == ".webm":
            crf = {"low": "40", "medium": "30", "high": "20", "lossless": "10"}.get(quality, "30")
            cmd += ["-b:v", "0", "-crf", crf, "-c:a", "libvorbis"]
        elif target_ext == ".ogv":
            cmd += ["-c:a", "libvorbis", "-q:v", "5"]
        else:
            crf = {"low": "32", "medium": "23", "high": "18", "lossless": "0"}.get(quality, "23")
            cmd += ["-crf", crf, "-preset", "medium"]
            if target_ext == ".mp4":
                cmd += ["-movflags", "+faststart"]
            acodec = "aac" if target_ext in (".mp4", ".mov", ".3gp") else "copy"
            cmd += ["-c:a", acodec]

    cmd.append(str(dest))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(f"ffmpeg falhou ({src.name} → {target_ext}): {stderr.decode()[-400:]}")

    return dest
