# syntax=docker/dockerfile:1
FROM python:3.11.7-slim AS base

# System deps (libgomp1 helps faiss-cpu; curl for debugging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better Docker cache)
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project
# If your code lives in a subfolder, copy the repo root and set WORKDIR below.
COPY . .

# Streamlit listens on 8501 and must bind 0.0.0.0 in a container
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    PYTHONUNBUFFERED=1

# Work from the folder that contains app.py
WORKDIR /app/Webly

# (Optional) Pre-pull the default embedding model to warm cache
# RUN python - <<'PY'
# from sentence_transformers import SentenceTransformer
# SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
# PY

EXPOSE 8501

# Default: run Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
