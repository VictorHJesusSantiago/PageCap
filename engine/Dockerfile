# PageCap engine — REST/WebSocket API + Chromium (via Playwright) + ffmpeg.
# Built from the repo root: `docker build -t pagecap-engine -f engine/Dockerfile .`
#
# The official Playwright image already bundles Chromium plus every OS-level
# library it needs (fonts, codecs, etc.) — building that stack manually on a
# plain python:slim base is a well-known source of "works on my machine"
# Playwright breakage, so we start from it instead of reinventing it.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app/engine

# ffmpeg is required for media conversion/muxing (converters/media.py,
# extractors/network.py's HLS/DASH mux) and isn't part of the Playwright image.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright's browser binaries are already baked into this base image; this
# just confirms they're present for the Python package version pinned above.
RUN python -m playwright install chromium --with-deps

COPY engine/ .

# The API binds to 127.0.0.1 by default (see CLAUDE.md: local-only by
# design). Inside a container that's not reachable from the host, so the
# entrypoint below explicitly binds 0.0.0.0 — treat the container boundary
# itself as the trust boundary (published ports, network policy) instead.
EXPOSE 8765

ENV PAGECAP_DB_PATH=/app/data/pagecap.db
VOLUME ["/app/data", "/app/engine/downloads"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8765"]
