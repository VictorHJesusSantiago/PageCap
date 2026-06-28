"""
Main orchestrator: runs all extraction strategies in sequence.

Strategy order (most specific → most general):
  1. Page → PDF           (always, if requested)
  2. yt-dlp               (platform-aware: YouTube, Vimeo, TikTok, 1800+ sites)
  3. Network interception  (any player, HLS/DASH, custom streams)
  4. DOM scan             (direct <audio>/<video> tags, linked files)
  5. Universal scanner    (ALL 150+ registered file types from DOM + network)
  6. Screen recording     (last resort: records what renders on screen)
  7. Post-download conv.  (convert each file to target format if requested)
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Optional

from playwright.async_api import async_playwright

from models import (
    AuthMethod,
    ContentType,
    ExtractedFile,
    ExtractionRequest,
    JobState,
    JobStatus,
)
from file_types import category_of
from auth.credentials import apply_credentials
from auth.cookies import load_cookies
from extractors.page import extract_page_pdf
from extractors.media import extract_media
from extractors.network import extract_via_network
from extractors.generic import extract_generic_media
from extractors.universal import extract_universal
from extractors.screen_record import extract_screen_record


# Map ContentType → file_types categories
_CT_TO_CATEGORIES: dict[str, set[str]] = {
    "all":       {"text", "spreadsheet", "presentation", "image", "vector", "audio", "video",
                  "font", "subtitle", "data", "code", "archive", "executable", "certificate",
                  "ml", "3d", "config"},
    "page_pdf":  set(),          # handled separately
    "images":    {"image", "vector"},
    "videos":    {"video"},
    "audio":     {"audio"},
    "documents": {"text", "spreadsheet", "presentation", "data", "subtitle"},
}


async def crawl_assets(
    request: ExtractionRequest,
    job: JobState,
    on_progress: Optional[Callable[[JobState], None]] = None,
) -> list[ExtractedFile]:
    """
    Main entry point. Runs all applicable extractors and returns all files found.
    Updates job state in place; calls on_progress after each change.
    """
    output_dir = Path(request.output_dir or f"downloads/{job.job_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    job.output_dir = str(output_dir)

    want = {ct.value for ct in request.content_types}
    want_all = ContentType.all.value in want
    want_media = want_all or ContentType.videos.value in want or ContentType.audio.value in want

    # Determine which categories to pass to the universal scanner
    wanted_categories: set[str] = set()
    for ct_val in want:
        wanted_categories |= _CT_TO_CATEGORIES.get(ct_val, set())

    # Explicit extension filter (fine-grained)
    wanted_extensions: set[str] | None = (
        set(request.target_extensions) if request.target_extensions else None
    )

    files: list[ExtractedFile] = []
    seen_filenames: set[str] = set()

    def _add(f: ExtractedFile):
        if f.filename not in seen_filenames:
            seen_filenames.add(f.filename)
            files.append(f)
            job.files.append(f)

    def _emit(msg: str, progress: int = -1):
        job.message = msg
        if progress >= 0:
            job.progress = progress
        if on_progress:
            on_progress(job)

    def _cancelled() -> bool:
        return job.status == JobStatus.cancelled

    _emit("Iniciando navegador...", 2)

    headless = not request.auth.manual_captcha

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

        # ── Authentication ────────────────────────────────────────────────────
        auth = request.auth
        page = await context.new_page()

        if auth.method == AuthMethod.cookies and auth.cookies_raw:
            _emit("Carregando cookies...", 5)
            n = await load_cookies(context, request.url, raw=auth.cookies_raw)
            _emit(f"{n} cookie(s) carregados", 8)

        elif auth.method == AuthMethod.cookies_browser and auth.cookies_browser:
            _emit(f"Importando cookies do {auth.cookies_browser}...", 5)
            n = await load_cookies(
                context, request.url,
                browser_name=auth.cookies_browser,
                profile=auth.cookies_profile,
            )
            _emit(f"{n} cookie(s) importados", 8)

        elif auth.method == AuthMethod.credentials and auth.username and auth.password:
            _emit("Realizando login...", 5)

            def _on_captcha(msg: str):
                job.status = JobStatus.waiting_captcha
                _emit(f"⚠ {msg}", 8)

            try:
                success = await apply_credentials(
                    page, request.url,
                    auth.username, auth.password,
                    manual_captcha=auth.manual_captcha,
                    on_captcha_detected=_on_captcha,
                )
                job.status = JobStatus.running
                _emit("Login concluído" if success else "Formulário não encontrado; continuando", 10)
            except Exception as e:
                _emit(f"Erro no login: {e}", 10)

        pw_cookies = await context.cookies()

        # ── 1. Page → PDF ─────────────────────────────────────────────────────
        if want_all or ContentType.page_pdf.value in want:
            _emit("Capturando página como PDF...", 12)
            try:
                async for f in extract_page_pdf(page, request.url, output_dir):
                    _add(f)
                    _emit(f"PDF: {f.filename}", 18)
            except Exception as e:
                _emit(f"PDF falhou: {e}", 18)

        # ── 2. yt-dlp (plataformas conhecidas) ───────────────────────────────
        if want_media and not _cancelled():
            _emit("Tentando yt-dlp (YouTube, Vimeo, TikTok, etc.)...", 20)
            try:
                async for f in extract_media(
                    request.url, output_dir, list(want), quality=request.quality,
                ):
                    _add(f)
                    _emit(f"yt-dlp: {f.filename}", 28)
            except Exception as e:
                _emit(f"yt-dlp: {e}", 28)

        # ── 3. Interceptação de rede ──────────────────────────────────────────
        if want_media and not _cancelled():
            _emit("Interceptando requisições de mídia...", 30)
            try:
                net_page = await context.new_page()
                async for f in extract_via_network(
                    net_page, request.url, output_dir, list(want),
                    cookies=pw_cookies,
                    wait_seconds=request.network_wait,
                ):
                    _add(f)
                    _emit(f"Rede: {f.filename}", 45)
                await net_page.close()
            except Exception as e:
                _emit(f"Interceptação: {e}", 45)

        # ── 4. DOM scan (tags diretas) ────────────────────────────────────────
        if want_media and not _cancelled():
            _emit("Escaneando tags de mídia no DOM...", 47)
            try:
                async for f in extract_generic_media(
                    page, request.url, output_dir, list(want), cookies=pw_cookies,
                ):
                    _add(f)
            except Exception as e:
                _emit(f"DOM scan: {e}", 50)

        # ── 5. Scanner universal (todos os 150+ tipos) ────────────────────────
        if not _cancelled():
            _emit("Scanner universal de arquivos...", 52)
            try:
                uni_page = await context.new_page()
                async for f in extract_universal(
                    uni_page, request.url, output_dir,
                    wanted_categories=wanted_categories if not want_all else None,
                    wanted_extensions=wanted_extensions,
                    cookies=pw_cookies,
                    max_files=request.max_files,
                    already_seen=set(seen_filenames),
                ):
                    _add(f)
                    _emit(f"Universal: {f.filename}", 80)
                await uni_page.close()
            except Exception as e:
                _emit(f"Scanner universal: {e}", 80)

        # ── 6. Gravação de tela ───────────────────────────────────────────────
        if request.screen_record and want_media and not _cancelled():
            _emit(f"Gravando tela por {request.screen_record_duration}s...", 82)
            try:
                async for f in extract_screen_record(
                    page, context, request.url, output_dir,
                    duration=request.screen_record_duration,
                ):
                    _add(f)
                    _emit(f"Gravação: {f.filename}", 90)
            except Exception as e:
                _emit(f"Gravação de tela: {e}", 90)

        await browser.close()

    # ── 7. Conversão pós-download ─────────────────────────────────────────────
    if request.convert_to and files and not _cancelled():
        target_ext = request.convert_to if request.convert_to.startswith(".") else f".{request.convert_to}"
        _emit(f"Convertendo arquivos para {target_ext}...", 92)
        converted_dir = output_dir / "converted"
        converted_dir.mkdir(exist_ok=True)

        from converter import convert_file, ConversionError

        for i, f in enumerate(files):
            if not f.local_path:
                continue
            src = Path(f.local_path)
            if src.suffix.lower() == target_ext:
                continue
            try:
                dest = await convert_file(src, target_ext, converted_dir)
                f.converted_path = str(dest)
                f.converted_ext = target_ext
                _emit(f"Convertido: {dest.name}", 92 + int(6 * i / len(files)))
            except ConversionError as e:
                _emit(f"Conversão ignorada ({src.name}): {e}", -1)
            if on_progress:
                on_progress(job)

    if _cancelled():
        job.message = f"Cancelado. {len(files)} arquivo(s) extraído(s) antes do cancelamento."
    else:
        job.status = JobStatus.done
        job.progress = 100
        job.message = f"Concluído. {len(files)} arquivo(s) extraído(s)."
    if on_progress:
        on_progress(job)

    return files
