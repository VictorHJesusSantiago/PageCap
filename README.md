# PageCap

Extrai qualquer tipo de conteúdo de qualquer página web: PDFs, vídeos, áudios, imagens e documentos. Funciona via interface gráfica (desktop ou browser) e linha de comando.

## Stack

| Camada | Tecnologia |
|---|---|
| Motor de extração | **Python** (Playwright, yt-dlp, httpx, FastAPI) |
| Tipos & cliente API | **TypeScript** (@pagecap/core) |
| Interface web | **React + Vite** (@pagecap/ui) |
| App desktop | **Electron** (@pagecap/electron) |

## Pré-requisitos

- Python 3.10+
- Node.js 18+
- npm 9+

## Instalação

**Windows:**
```bat
setup.bat
```

**Linux / macOS:**
```sh
chmod +x setup.sh && ./setup.sh
```

## Uso

### Interface Web (browser)

```sh
npm run dev:web
```
Abra `http://localhost:5173` no browser.

### App Desktop (Electron)

```sh
npm run dev
```

### CLI (linha de comando)

```sh
cd engine

# Extrai tudo de uma página
python cli.py https://exemplo.com --type all

# Só vídeos e áudio
python cli.py https://youtube.com/watch?v=xxx --type videos,audio

# Página como PDF, com login
python cli.py https://intranet.empresa.com --type page_pdf \
    --username usuario --password senha

# Usando cookies do Chrome
python cli.py https://netflix.com --type videos --browser chrome

# Colando cookies manualmente
python cli.py https://site.com --type images \
    --cookies "session=abc123; token=xyz"

# Saída JSON
python cli.py https://exemplo.com --type images --json

# Ver todas as opções
python cli.py --help
```

### Servidor da API (para integração custom)

```sh
cd engine
python cli.py server --port 8765
# ou diretamente:
uvicorn api:app --host 127.0.0.1 --port 8765
```

## Tipos de conteúdo suportados

| Tipo | Flag CLI | Descrição |
|---|---|---|
| Tudo | `all` | Extrai todos os tipos abaixo |
| Página PDF | `page_pdf` | Captura a página inteira como PDF |
| Imagens | `images` | JPG, PNG, GIF, WebP, SVG, AVIF |
| Vídeos | `videos` | MP4 e qualquer formato suportado pelo yt-dlp (YouTube, Vimeo, 1000+ sites) |
| Áudio | `audio` | MP3, qualquer áudio via yt-dlp |
| Documentos | `documents` | PDF, Word, Excel, PowerPoint, ZIP, EPUB e outros |

## Autenticação

| Método | Quando usar |
|---|---|
| Nenhuma | Sites públicos |
| Login/Senha | Sites com formulário de login (ex: intranets, portais) |
| Cookies (texto) | Cole o header de cookies da aba Network do DevTools |
| Cookies do browser | Importa sessão ativa do Chrome/Firefox/Edge/Brave diretamente |

## Estrutura do projeto

```
PageCap/
├── engine/                   # Python
│   ├── api.py                # FastAPI REST + WebSocket
│   ├── cli.py                # CLI (Typer)
│   ├── config.py             # Configuração (fonte única, lida no import)
│   ├── models.py             # Pydantic models
│   ├── crypto_box.py         # AES-256-GCM para segredos em repouso
│   ├── problem_details.py    # Erros RFC 7807
│   ├── job_store.py          # Persistência de jobs (SQLite)
│   ├── stores.py             # Credenciais / templates / schedules
│   ├── auth/
│   │   ├── credentials.py    # Login automático via Playwright
│   │   ├── cookies.py        # Importação de cookies
│   │   └── tokens.py         # Token da API (gera/persiste)
│   ├── converters/           # Conversão pós-download por categoria
│   └── extractors/
│       ├── crawler.py        # Orquestrador (pipeline de estágios)
│       ├── page.py           # Página → PDF
│       ├── media.py          # Vídeo/áudio (yt-dlp)
│       ├── network.py        # Interceptação de rede, HLS/DASH
│       └── universal.py      # Scanner de todos os 150+ tipos
├── packages/
│   ├── core/                 # TypeScript: tipos + cliente HTTP
│   ├── ui/                   # React + Vite (interface web)
│   └── electron/             # Wrapper Electron (app desktop)
├── docs/adr/                 # Decisões de arquitetura
├── setup.bat                 # Setup Windows
└── setup.sh                  # Setup Linux/macOS
```

## Desenvolvimento

```sh
npm run typecheck          # tsc --noEmit nos três workspaces
npm test                   # testes do engine (pytest) + frontend (Vitest)
npm run test:engine        # só Python
npm run test:ui            # só frontend (RTL + axe)
```

CI (`.github/workflows/ci.yml`) roda: pytest, `pip-audit`, `npm audit` das
dependências de runtime, typecheck, Vitest com gate de cobertura, os três builds
e o build da imagem Docker.

## Licença

MIT — ver [LICENSE](LICENSE).

## API REST

Após iniciar o servidor (`npm run dev:engine`). Documentação interativa em
`http://127.0.0.1:8765/docs`.

### Autenticação

**A API exige um token por padrão.** Se você não definir `PAGECAP_API_TOKEN`, o
servidor gera um no primeiro boot e o grava em `.pagecap_token`, ao lado do
banco. Para obtê-lo:

```sh
cd engine && python cli.py token --show
```

Envie como header (preferido) ou, para URLs que o browser busca sozinho
(`<img src>`, `<a download>`, WebSocket), como query param:

```sh
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8765/v1/health
curl "http://127.0.0.1:8765/v1/jobs/abc/download/foto.jpg?token=$TOKEN" -O
```

Por que isso é obrigatório: `127.0.0.1` **não** é uma fronteira de confiança.
Qualquer site que você visita pode fazer requisições para a porta local. Ver
[`docs/adr/ADR-001`](docs/adr/ADR-001-local-api-trust-boundary.md).

O app Electron cuida disso sozinho (gera um token novo por execução e o injeta
no renderer) — nada a configurar.

### Endpoints

Todos sob o prefixo `/v1`. Os caminhos sem versão continuam funcionando, mas
respondem com `Deprecation`/`Sunset` — ver
[`docs/adr/ADR-002`](docs/adr/ADR-002-api-versioning.md).

| Endpoint | Método | Descrição |
|---|---|---|
| `/v1/health` | GET | Status + métricas de jobs (sem auth) |
| `/v1/health/live` | GET | Liveness probe (sem auth) |
| `/v1/health/ready` | GET | Readiness probe: verifica o datastore (sem auth) |
| `/v1/metrics` | GET | Métricas RED (rate/errors/duration, com percentis) |
| `/v1/extract` | POST | Inicia extração → `202` + `Location` |
| `/v1/jobs` | GET | Histórico paginado por cursor (`?limit=&cursor=`) |
| `/v1/jobs/{id}` | GET | Status do job |
| `/v1/jobs/{id}/files` | GET | Lista arquivos extraídos |
| `/v1/jobs/{id}/download/{filename}` | GET | Baixa um arquivo |
| `/v1/jobs/{id}/preview/{filename}` | GET | Serve inline (só imagem/áudio/vídeo) |
| `/v1/jobs/{id}/download-all` | GET | Baixa tudo como `.zip` |
| `/v1/jobs/{id}` | DELETE | Cancela job |
| `/v1/jobs/{id}/pause` · `/resume` | POST | Pausa / retoma |
| `/v1/credentials` · `/templates` · `/schedules` | GET/POST/DELETE | Presets salvos |
| `/v1/ws/{id}` | WebSocket | Progresso em tempo real |

Erros seguem RFC 7807 (`application/problem+json`) e incluem um `traceId` que
casa com o header `X-Request-ID` e com o campo `request_id` nos logs JSON.

### Configuração

Todas as variáveis de ambiente estão documentadas em
[`.env.example`](.env.example).

## Construir distribuível (Electron)

```sh
npm run dist --workspace=packages/electron
# Gera instalador em packages/electron/release/
```
