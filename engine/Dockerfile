FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app/engine

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tini \
    && rm -rf /var/lib/apt/lists/*

COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install chromium --with-deps

COPY engine/ .

ENV PAGECAP_DB_PATH=/app/data/pagecap.db
RUN mkdir -p /app/data /app/engine/downloads \
    && chown -R pwuser:pwuser /app

EXPOSE 8765
VOLUME ["/app/data", "/app/engine/downloads"]

USER pwuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health/ready', timeout=3)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8765"]
