"""
Central conversion orchestrator.
Routes file to the correct converter based on source and target extension.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from file_types import get_info, conversions_for, category_of


class ConversionError(Exception):
    pass


# Category → converter function name
_CATEGORY_CONVERTER = {
    "text":         "document",
    "spreadsheet":  "data",
    "presentation": "document",    # pandoc handles pptx → pdf etc.
    "image":        "image",
    "vector":       "image",
    "audio":        "media",
    "video":        "media",
    "font":         "font",
    "subtitle":     "subtitle",
    "data":         "data",
    "code":         "document",    # highlight → html/pdf via pandoc
    "config":       "document",
}


async def convert_file(
    src: Path,
    target_ext: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Convert `src` to `target_ext`.
    If `output_dir` is given, the converted file is placed there.
    Returns the path of the converted file.

    Raises ConversionError on failure.
    """
    src_ext = src.suffix.lower()
    target_ext = target_ext.lower()

    if src_ext == target_ext:
        return src

    # Validate that this conversion is registered
    allowed = conversions_for(src_ext)
    if allowed and target_ext not in allowed:
        raise ConversionError(
            f"Conversão {src_ext} → {target_ext} não é suportada. "
            f"Destinos válidos: {', '.join(allowed)}"
        )

    cat = category_of(src_ext)
    converter_name = _CATEGORY_CONVERTER.get(cat)
    if not converter_name:
        raise ConversionError(
            f"Nenhum conversor disponível para arquivos da categoria '{cat}' ({src_ext})"
        )

    try:
        if converter_name == "document":
            from converters.document import convert_document
            dest = await convert_document(src, target_ext)
        elif converter_name == "image":
            from converters.image import convert_image
            dest = await convert_image(src, target_ext)
        elif converter_name == "media":
            from converters.media import convert_media
            dest = await convert_media(src, target_ext)
        elif converter_name == "data":
            from converters.data import convert_data
            dest = await convert_data(src, target_ext)
        elif converter_name == "font":
            from converters.font import convert_font
            dest = await convert_font(src, target_ext)
        elif converter_name == "subtitle":
            from converters.subtitle import convert_subtitle
            dest = await convert_subtitle(src, target_ext)
        else:
            raise ConversionError(f"Conversor desconhecido: {converter_name}")
    except ConversionError:
        raise
    except Exception as e:
        raise ConversionError(f"Conversão falhou ({src.name} → {target_ext}): {e}") from e

    # Move to output_dir if specified
    if output_dir and dest.parent != output_dir:
        final = output_dir / dest.name
        dest.rename(final)
        return final

    return dest


def available_conversions(src_path: str | Path) -> list[str]:
    """Return list of target extensions this file can be converted to."""
    ext = Path(src_path).suffix.lower()
    return conversions_for(ext)


async def batch_convert(
    files: list[Path],
    target_ext: str,
    output_dir: Optional[Path] = None,
    on_done: Optional[callable] = None,
) -> list[tuple[Path, Path | Exception]]:
    """
    Convert multiple files to the same target format concurrently (max 4 at once).
    Returns list of (src, dest_or_exception) tuples.
    """
    sem = asyncio.Semaphore(4)
    results: list[tuple[Path, Path | Exception]] = []

    async def _one(f: Path):
        async with sem:
            try:
                dest = await convert_file(f, target_ext, output_dir)
                result = (f, dest)
            except Exception as e:
                result = (f, e)
            results.append(result)
            if on_done:
                on_done(result)
            return result

    await asyncio.gather(*(_one(f) for f in files))
    return results
