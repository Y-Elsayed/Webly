# Changelog

All notable changes to Webly will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Webly uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.1.0] — 2026-04-06

Initial public release.

### Added
- **Ingest pipeline** — crawl any website, chunk HTML with heading-aware sliding windows, embed with OpenAI or HuggingFace, store in FAISS
- **Query pipeline** — multi-hop semantic retrieval with BM25 hybrid search, graph-link expansion, section expansion, and LLM re-ranking
- **Builder retrieval mode** — concept-aware context builder that identifies missing coverage and issues targeted follow-up searches
- **Streamlit UI** — project/chat management, live crawl progress, settings editor with per-project system prompt overrides
- **OpenAI embedder** — `text-embedding-3-small` and `text-embedding-3-large` with retry/backoff
- **HuggingFace embedder** — any `sentence-transformers` model usable locally
- **FAISS vector database** — flat, HNSW, IVF-flat, and IVF-PQ index types; cosine similarity via L2 normalisation; stable deterministic IDs
- **Abstract base classes** — `Embedder`, `VectorDatabase`, `Chatbot`, `TextExtractor`, `TextChunker`, `BaseCrawler` for framework extension
- **SSRF protection** — crawler blocks private/loopback/link-local IP addresses and non-HTTP(S) schemes
- **Path traversal protection** — project and chat names sanitised before filesystem operations
- **Docker support** — `Dockerfile` with health check; `docker-compose.yml` with volume persistence
- **CI** — GitHub Actions: lint (ruff) + tests (pytest) on every push/PR
- **`pyproject.toml`** — pip-installable with optional extras (`[hf]`, `[ui]`, `[dev]`, `[all]`)

### Changed
- Debug logging now defaults to `False`; enable per-project via `debug` / `query_debug` config keys
- All pipeline `print()` calls replaced with `logging` module calls routed through file + console handlers

### Security
- `StorageManager._sanitize_name()` prevents path traversal on project and chat names
- `BaseAgent._is_ssrf_target()` blocks requests to private network ranges and cloud metadata endpoints

[Unreleased]: https://github.com/Y-Elsayed/webly/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Y-Elsayed/webly/releases/tag/v0.1.0
