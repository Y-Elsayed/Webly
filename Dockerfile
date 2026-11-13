# syntax=docker/dockerfile:1
FROM python:3.12-slim AS wheels
WORKDIR /build
RUN python -m pip install --no-cache-dir 'setuptools>=68' wheel
COPY webcreeper/pyproject.toml webcreeper/README.md webcreeper/LICENSE ./crawler/
COPY webcreeper/webcreeper ./crawler/webcreeper
RUN python -m pip wheel --no-deps --no-build-isolation ./crawler --wheel-dir /wheels
COPY pyproject.toml MANIFEST.in README.md LICENSE NOTICE ./core/
COPY webly ./core/webly
RUN python -m pip wheel --no-deps --no-build-isolation ./core --wheel-dir /wheels

FROM python:3.12-slim AS core
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=wheels /wheels /tmp/wheels
RUN python -m pip install --no-cache-dir /tmp/wheels/*.whl \
 && rm -rf /tmp/wheels \
 && useradd --uid 10001 --create-home webly \
 && mkdir -p /data /app/log && chown -R webly:webly /data /app/log
WORKDIR /app
USER webly
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 WEBLY_STORAGE_ROOT=/data
CMD ["python", "-c", "import webly; print('Webly Core installed; supply the host worker command')"]

FROM core AS checks
USER root
RUN python -m pip install --no-cache-dir pytest psutil
COPY scripts /app/scripts
COPY tests/test_core_v2.py tests/test_capture_policy.py tests/test_html_extraction.py /app/tests/
USER webly
CMD ["python", "-m", "scripts.single_host_checks", "--output", "/data/single-host.json"]

# Private reference UI; the SaaS supplies its own authorized application/worker.
FROM core AS ui
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && python -m pip install --no-cache-dir 'webly[ui]'
COPY app.py ./app.py
USER webly
ENV STREAMLIT_SERVER_PORT=8501 STREAMLIT_SERVER_ADDRESS=0.0.0.0
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
 CMD curl -f http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
