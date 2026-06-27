"""PageCap CLI — extract any content from web pages."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from models import (
    AuthConfig,
    AuthMethod,
    ContentType,
    CookiesBrowser,
    ExtractionRequest,
    JobState,
    JobStatus,
)
from extractors.crawler import crawl_assets

app = typer.Typer(
    name="pagecap",
    help="Extrai qualquer tipo de conteúdo de páginas web.",
    rich_markup_mode="rich",
)
console = Console()


def _print_types():
    from file_types import REGISTRY, categories
    from rich.table import Table
    for cat in categories():
        tbl = Table(title=f"[bold]{cat.upper()}[/bold]", show_lines=True)
        tbl.add_column("Extensão", style="cyan")
        tbl.add_column("Nome")
        tbl.add_column("MIME")
        tbl.add_column("Converte para")
        seen = set()
        for ext, info in REGISTRY.items():
            if info.category == cat and info.ext not in seen:
                seen.add(info.ext)
                tbl.add_row(
                    info.ext,
                    info.label,
                    info.mime,
                    ", ".join(info.can_convert_to) or "—",
                )
        console.print(tbl)


def _parse_types(value: str) -> list[ContentType]:
    parts = [p.strip() for p in value.split(",")]
    result = []
    for p in parts:
        try:
            result.append(ContentType(p))
        except ValueError:
            console.print(f"[red]Tipo inválido: {p}[/red]")
            console.print(f"Tipos válidos: {', '.join(ct.value for ct in ContentType)}")
            raise typer.Exit(1)
    return result


@app.command()
def extract(
    url: str = typer.Argument(..., help="URL da página a extrair"),
    output: Path = typer.Option(
        Path("./downloads"),
        "--output", "-o",
        help="Diretório de saída",
    ),
    types: str = typer.Option(
        "all",
        "--type", "-t",
        help="Tipos a extrair (separados por vírgula): all, page_pdf, images, videos, audio, documents",
    ),
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Nome de usuário para login"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Senha para login"),
    cookies: Optional[str] = typer.Option(None, "--cookies", "-c", help="Arquivo de cookies (formato Netscape) ou string 'key=val; key2=val2'"),
    browser: Optional[str] = typer.Option(None, "--browser", "-b", help="Importar cookies do browser: chrome, firefox, edge, brave"),
    browser_profile: Optional[str] = typer.Option(None, "--profile", help="Caminho do perfil do browser (opcional)"),
    quality: str = typer.Option("best", "--quality", "-q", help="Qualidade de vídeo: best | worst"),
    json_output: bool = typer.Option(False, "--json", help="Saída em formato JSON"),
    manual_captcha: bool = typer.Option(False, "--captcha", help="Abre browser visível para CAPTCHA/2FA manual"),
    screen_record: bool = typer.Option(False, "--screen-record", "-s", help="Grava a tela como fallback para conteúdo protegido"),
    screen_duration: int = typer.Option(60, "--record-duration", help="Duração da gravação de tela em segundos"),
    network_wait: int = typer.Option(12, "--network-wait", help="Segundos aguardando requisições de mídia (interceptação)"),
    extensions: Optional[str] = typer.Option(None, "--ext", "-e", help="Extensões específicas separadas por vírgula: .pdf,.mp3,.xlsx"),
    convert_to: Optional[str] = typer.Option(None, "--convert", help="Converter arquivos baixados para este formato: ex. .mp3, .pdf, .png"),
    list_types: bool = typer.Option(False, "--list-types", help="Lista todos os tipos de arquivos suportados e saí"),
):
    """
    [bold]PageCap[/bold] — Extrai qualquer tipo de arquivo de uma página web.

    Exemplos:

      pagecap https://example.com --type all

      pagecap https://site.com/video --type videos,audio

      pagecap https://intranet.com --username admin --password s3cr3t --type page_pdf

      pagecap https://netflix.com --browser chrome --type videos
    """
    if list_types:
        _print_types()
        raise typer.Exit()

    content_types = _parse_types(types)

    # Auth config
    auth = AuthConfig()
    if manual_captcha:
        auth.manual_captcha = True

    if username and password:
        auth.method = AuthMethod.credentials
        auth.username = username
        auth.password = password
    elif cookies:
        auth.method = AuthMethod.cookies
        cookies_path = Path(cookies)
        if cookies_path.exists():
            auth.cookies_raw = cookies_path.read_text(encoding="utf-8")
        else:
            auth.cookies_raw = cookies
    elif browser:
        auth.method = AuthMethod.cookies_browser
        try:
            auth.cookies_browser = CookiesBrowser(browser.lower())
        except ValueError:
            console.print(f"[red]Browser inválido: {browser}[/red]")
            console.print("Browsers suportados: chrome, firefox, edge, brave, opera, safari")
            raise typer.Exit(1)
        auth.cookies_profile = browser_profile

    output.mkdir(parents=True, exist_ok=True)

    target_exts = [e.strip() if e.startswith(".") else f".{e.strip()}"
                   for e in extensions.split(",") if e.strip()] if extensions else []

    request = ExtractionRequest(
        url=url,
        content_types=content_types,
        target_extensions=target_exts,
        auth=auth,
        output_dir=str(output),
        quality=quality,
        network_wait=network_wait,
        screen_record=screen_record,
        screen_record_duration=screen_duration,
        convert_to=convert_to,
    )

    import uuid
    job = JobState(job_id=str(uuid.uuid4()), url=url)

    if json_output:
        asyncio.run(_run_json(request, job))
    else:
        asyncio.run(_run_rich(request, job))


async def _run_rich(request: ExtractionRequest, job: JobState):
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Iniciando...", total=100)

        def on_progress(j: JobState):
            progress.update(task, completed=j.progress, description=j.message)

        try:
            files = await crawl_assets(request, job, on_progress=on_progress)
        except Exception as e:
            console.print(f"\n[red]Erro: {e}[/red]")
            raise typer.Exit(1)

    console.print()
    if not files:
        console.print("[yellow]Nenhum arquivo extraído.[/yellow]")
        return

    table = Table(title=f"[bold green]{len(files)} arquivo(s) extraído(s)[/bold green]")
    table.add_column("Arquivo", style="cyan")
    table.add_column("Tipo")
    table.add_column("Tamanho")
    table.add_column("Local")

    for f in files:
        size = f"{f.size_bytes / 1024:.1f} KB" if f.size_bytes else "?"
        table.add_row(f.filename, f.content_type, size, f.local_path or "")

    console.print(table)
    console.print(f"\n[bold]Saída:[/bold] {request.output_dir}")


async def _run_json(request: ExtractionRequest, job: JobState):
    files = await crawl_assets(request, job)
    print(json.dumps([f.model_dump() for f in files], indent=2, ensure_ascii=False))


@app.command()
def server(
    host: str = typer.Option("127.0.0.1", "--host", help="Host do servidor"),
    port: int = typer.Option(8765, "--port", help="Porta do servidor"),
    reload: bool = typer.Option(False, "--reload", help="Recarregar automaticamente em mudanças"),
):
    """Inicia o servidor da API (para a interface gráfica)."""
    import uvicorn
    console.print(f"[bold]PageCap API[/bold] rodando em http://{host}:{port}")
    uvicorn.run("api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
