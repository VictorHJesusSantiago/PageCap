"""
Central conversion orchestrator.
Routes file to the correct converter based on source and target extension.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable, Optional

from file_types import conversions_for, category_of


class ConversionError(Exception):
    pass


ConverterFn = Callable[[Path, str], Awaitable[Path]]


def _load_document() -> ConverterFn:
    from converters.document import convert_document
    return convert_document


def _load_image() -> ConverterFn:
    from converters.image import convert_image
    return convert_image


def _load_media() -> ConverterFn:
    from converters.media import convert_media
    return convert_media


def _load_data() -> ConverterFn:
    from converters.data import convert_data
    return convert_data


def _load_font() -> ConverterFn:
    from converters.font import convert_font
    return convert_font


def _load_subtitle() -> ConverterFn:
    from converters.subtitle import convert_subtitle
    return convert_subtitle


_CONVERTER_LOADERS: dict[str, Callable[[], ConverterFn]] = {
    "document": _load_document,
    "image": _load_image,
    "media": _load_media,
    "data": _load_data,
    "font": _load_font,
    "subtitle": _load_subtitle,
}

_CATEGORY_CONVERTER: dict[str, str] = {
    "text":         "document",
    "spreadsheet":  "data",
    "presentation": "document",
    "image":        "image",
    "vector":       "image",
    "audio":        "media",
    "video":        "media",
    "font":         "font",
    "subtitle":     "subtitle",
    "data":         "data",
    "code":         "document",
    "config":       "document",
}

assert set(_CATEGORY_CONVERTER.values()) <= set(_CONVERTER_LOADERS), (
    "_CATEGORY_CONVERTER references an unknown converter: "
    f"{set(_CATEGORY_CONVERTER.values()) - set(_CONVERTER_LOADERS)}"
)


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

    allowed = conversions_for(src_ext)
    if target_ext not in allowed:
        supported = ', '.join(allowed) if allowed else "nenhum"
        raise ConversionError(
            f"Conversão {src_ext} → {target_ext} não é suportada. "
            f"Destinos válidos: {supported}"
        )

    cat = category_of(src_ext)
    converter_name = _CATEGORY_CONVERTER.get(cat)
    if not converter_name:
        raise ConversionError(
            f"Nenhum conversor disponível para arquivos da categoria '{cat}' ({src_ext})"
        )

    try:
        convert = _CONVERTER_LOADERS[converter_name]()
        dest = await convert(src, target_ext)
    except ConversionError:
        raise
    except Exception as e:
        raise ConversionError(f"Conversão falhou ({src.name} → {target_ext}): {e}") from e

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
    on_done: Optional[Callable[[tuple[Path, Path | Exception]], None]] = None,
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
