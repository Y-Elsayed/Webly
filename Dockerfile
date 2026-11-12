# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY webcreeper/pyproject.toml webcreeper/README.md webcreeper/LICENSE /tmp/webcreeper/
COPY webcreeper/webcreeper /tmp/webcreeper/webcreeper
RUN python -m pip install --upgrade pip \
 && pip install --no-cache-dir /tmp/webcreeper

COPY pyproject.toml MANIFEST.in README.md LICENSE NOTICE ./
COPY webly ./webly
COPY app.py ./app.py
RUN pip install --no-cache-dir '.[ui]' \
 && useradd --uid 10001 --create-home webly \
 && mkdir -p /data /app/log \
 && chown -R webly:webly /data /app/log
USER webly

ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WEBLY_STORAGE_ROOT=/data

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
