# Webly — LinkedIn Context (Full, Updated)

## One‑line Summary
Webly is a modular, GenAI‑powered web crawler and RAG framework that turns any website into a searchable, chat‑ready knowledge base with a Streamlit UI.

## What It Does
- Crawls websites (full site, patterns, or specific pages)
- Extracts and chunks content with structure (headings, anchors)
- Optionally summarizes
- Embeds and indexes content (FAISS by default)
- Provides a chat interface to query the site
- Builds a site graph for structure‑aware retrieval

## Key Features
- Modular pipeline: crawl → extract → chunk → embed → store → query
- Pluggable components: embeddings, vector DBs, processors
- Streamlit UI for projects, runs, and chats
- Graph + section expansion in retrieval
- Hybrid retrieval (vector + BM25) for better recall
- Safe crawling defaults (robots.txt, rate limiting)

## Current Retrieval (How It Works)
- Vector search (FAISS)
- Hybrid BM25 search (keyword matching)
- Merge + rerank with weighted scoring
- Graph expansion using anchors
- Section expansion using headings
- Answerability check + best‑effort fallback

## UI / UX Updates (Latest)
- Tabbed UI: Overview / Run / Chat / Settings
- Per‑chat memory with truncation + Clear Memory button per chat
- Pinned chat input (CSS) while keeping Streamlit’s default look
- Immediate render of user message after submit

## Why It’s Useful
- Turn documentation sites or knowledge bases into chat/search tools
- Build RAG pipelines quickly without heavy infra
- Useful for internal knowledge search, FAQs, customer support

## What’s Unique / Interesting
- Custom crawler (WebCreeper) built from scratch
- Graph‑aware retrieval (anchor + section expansion)
- Hybrid retrieval for better recall
- Streamlit UI to manage projects and chats

## Project Structure (High Level)
- `crawl/` — crawler wrapper
- `webcreeper/` — crawler engine
- `processors/` — extractors, chunkers, summarizer
- `embedder/` — embedding backends
- `vector_index/` — FAISS wrapper
- `pipeline/` — ingest & query orchestration
- `app.py` — Streamlit UI

## Usage
- Run UI: `streamlit run app.py`
- Configure projects and crawl settings in the sidebar
- Run Crawl + Index
- Chat with the site

## Dependencies (Now Split)
- `requirements.txt` = minimal runtime
- `requirements-ml.txt` = HF embeddings + summarization stack
- `requirements-dev.txt` = tests + lint
- `requirements-full.txt` = legacy all‑in‑one list

## Docker
- Optional ML deps with `--build-arg INSTALL_ML=true`
- Streamlit runs on `:8501`

## Testing
- Pytest + Ruff in CI
- Tests cover crawler policies, ingest pipeline, FAISS round‑trip

## Roadmap Highlights
**Crawler**
- Async crawling
- Robots crawl‑delay support
- Resume support
- JS rendering (Playwright)

**Retrieval**
- Hybrid search (done)
- Cross‑encoder reranking
- Eval harness

**Processing**
- Stronger chunking & metadata
- Language‑aware chunking

**Storage**
- Qdrant / Milvus adapters

## Open‑Source Readiness
- CI (pytest + ruff)
- CONTRIBUTING / CODE_OF_CONDUCT / SECURITY / ROADMAP
- Defaults respect robots.txt and rate‑limit

## Suggested LinkedIn Framing
- “Open‑sourcing an early‑stage but functional RAG pipeline for websites”
- Emphasize modularity, crawler built from scratch, and contributor‑friendly roadmap
- Ask for feedback or contributors in crawling, retrieval, and UI

## Notes for LinkedIn Post
- It’s early‑stage, not enterprise‑grade yet
- Clear scope: website → searchable RAG
- Invite collaborators
