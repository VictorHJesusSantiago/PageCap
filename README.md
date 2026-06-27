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
│   ├── models.py             # Pydantic models
│   ├── auth/
│   │   ├── credentials.py   # Login automático via Playwright
│   │   └── cookies.py       # Importação de cookies
│   └── extractors/
│       ├── crawler.py        # Orquestrador principal
│       ├── page.py           # Página → PDF
│       ├── media.py          # Vídeo/áudio (yt-dlp)
│       ├── images.py         # Imagens
│       └── documents.py      # Documentos
├── packages/
│   ├── core/                 # TypeScript: tipos + cliente HTTP
│   ├── ui/                   # React + Vite (interface web)
│   └── electron/             # Wrapper Electron (app desktop)
├── setup.bat                 # Setup Windows
└── setup.sh                  # Setup Linux/macOS
```

## API REST

Após iniciar o servidor (`npm run dev:engine`):

| Endpoint | Método | Descrição |
|---|---|---|
| `/health` | GET | Status da API |
| `/extract` | POST | Inicia extração |
| `/jobs/{id}` | GET | Status do job |
| `/jobs/{id}/files` | GET | Lista arquivos extraídos |
| `/jobs/{id}/download/{filename}` | GET | Baixa um arquivo |
| `/jobs/{id}` | DELETE | Cancela job |
| `/ws/{id}` | WebSocket | Progresso em tempo real |

## Construir distribuível (Electron)

```sh
npm run dist --workspace=packages/electron
# Gera instalador em packages/electron/release/
```
