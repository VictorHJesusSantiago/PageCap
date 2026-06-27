"""
Document converter: txt, md, html, docx, odt, pdf, rtf, epub, tex, rst, etc.
Backend: pandoc (must be installed and in PATH).
Fallback for pdf→txt: pdfminer.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

# pandoc format names differ from extensions
_PANDOC_FMT: dict[str, str] = {
    ".txt":   "plain",
    ".md":    "markdown",
    ".markdown": "markdown",
    ".html":  "html",
    ".htm":   "html",
    ".docx":  "docx",
    ".odt":   "odt",
    ".rtf":   "rtf",
    ".epub":  "epub",
    ".tex":   "latex",
    ".rst":   "rst",
    ".pdf":   "pdf",
    ".man":   "man",
    ".org":   "org",
    ".json":  "json",
    ".xml":   "docbook",
    ".wiki":  "mediawiki",
}


def _has_pandoc() -> bool:
    return shutil.which("pandoc") is not None


async def convert_document(src: Path, target_ext: str) -> Path:
    """
    Convert `src` document to `target_ext` (e.g. ".pdf", ".html", ".docx").
    Returns path to converted file.
    Raises RuntimeError if pandoc is not found or conversion fails.
    """
    if not _has_pandoc():
        raise RuntimeError(
            "pandoc não encontrado. Instale em https://pandoc.org/installing.html"
        )

    src_ext = src.suffix.lower()
    dest = src.with_suffix(target_ext)

    from_fmt = _PANDOC_FMT.get(src_ext, src_ext.lstrip("."))
    to_fmt = _PANDOC_FMT.get(target_ext, target_ext.lstrip("."))

    cmd = [
        "pandoc",
        str(src),
        "-f", from_fmt,
        "-t", to_fmt,
        "-o", str(dest),
        "--standalone",
    ]

    # PDF output requires a PDF engine
    if target_ext == ".pdf":
        if shutil.which("pdflatex"):
            cmd += ["--pdf-engine", "pdflatex"]
        elif shutil.which("weasyprint"):
            cmd += ["--pdf-engine", "weasyprint"]
        elif shutil.which("wkhtmltopdf"):
            cmd += ["--pdf-engine", "wkhtmltopdf"]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        # Fallback: pdf→txt via pdfminer
        if src_ext == ".pdf" and target_ext == ".txt":
            return await _pdf_to_txt(src, dest)
        raise RuntimeError(f"pandoc falhou: {stderr.decode()[:500]}")

    return dest


async def _pdf_to_txt(src: Path, dest: Path) -> Path:
    """Extract text from PDF using pdfminer.six as pandoc fallback."""
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(str(src))
        dest.write_text(text, encoding="utf-8")
        return dest
    except ImportError:
        raise RuntimeError(
            "pdfminer.six não instalado. Execute: pip install pdfminer.six"
        )
