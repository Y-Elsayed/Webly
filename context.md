# Webly Repository Context

## Purpose
Webly is a modular, GenAI-powered web crawling and knowledge extraction framework. It crawls a website, extracts and chunks text, optionally summarizes it, embeds chunks into vectors, stores them in a FAISS index, and exposes a chat/search experience over the site content. The project includes a Streamlit UI for managing projects and chats.

## High-Level Architecture
- Crawl layer (WebCreeper Atlas): fetches HTML pages, enforces crawl policies, and builds a link graph.
- Processing layer: extracts readable text, chunks it with structural context, and optionally summarizes.
- Embedding layer: generates vector embeddings using Hugging Face or OpenAI models.
- Storage layer: persists vectors and metadata in FAISS and saves per-project configs and chats.
- Query layer: retrieves relevant chunks, expands via link graph/sections, and answers with an LLM.
- UI layer: Streamlit app for project setup, runs, and chats.

## Entry Points
- `app.py`: Streamlit UI for project management, crawling/indexing runs, and chat sessions.
- `main.py`: builds ingest and query pipelines from a config dict. No CLI wrapper here; it is imported by the Streamlit app.
- Docker: `Dockerfile` runs `streamlit run app.py`.

## Core Data Flow
1. User creates a project in Streamlit with a start URL and settings.
2. Ingest pipeline runs:
   - Crawler fetches pages and writes results to `results.jsonl`.
   - Atlas also writes `graph.json` containing link graph with anchor text.
   - Processor extracts text and chunks it with headings/anchors.
   - Optional summarizer generates summaries per chunk and embeds summaries instead of raw text.
   - Embedder generates vectors for chunks (with internal splitting for max token limits).
   - FAISS index and metadata are written to `index/`.
3. Query pipeline runs:
   - Embed user query and search FAISS.
   - Optionally rewrite query and perform multi-hop retrieval.
   - Expand results via link graph and section headings.
   - Assemble context and answer via LLM.
   - If not answerable, return a fallback and helpful links.

## Repository Layout
Top-level files:
- `README.md`: user-facing overview. It contains visible encoding artifacts (non-ASCII glyphs), so be cautious when editing.
- `app.py`: Streamlit UI and session logic.
- `main.py`: pipeline factory.
- `requirements.txt`: Python deps.
- `Dockerfile`, `docker-compose.yml`: container setup.
- `Todo.md`: future features.
- `notes.txt`: Python version preference.

Key folders:
- `crawl/`: crawler wrapper used by the ingest pipeline.
- `processors/`: text extraction, chunking, summarization.
- `embedder/`: Hugging Face and OpenAI embedders.
- `pipeline/`: ingest/query orchestration and a lightweight embed-and-store pipeline.
- `vector_index/`: FAISS vector DB wrapper and interface.
- `storage/`: project/chats persistence.
- `webcreeper/`: internal crawler framework (Atlas agent and base crawler utilities).
- `websites_storage/`: default on-disk storage root for project configs, indices, and chats.

## Streamlit UI (`app.py`)
- Sets `STORAGE_ROOT` to `websites_storage` under repo root.
- Provides an OpenAI API key input with minimal validation (`OpenAI().models.list()`).
- Project creation:
  - Creates a per-project folder with `config.json` and `index/` and `chats/` subfolders.
  - Defaults to MiniLM HF embedder and `gpt-4o-mini` chat model.
- Project settings UI covers:
  - Crawl settings: start URL, allowed domains, path and URL pattern allow/block lists, max depth, rate limiting, allow subdomains, robots.txt.
  - Index settings: embedding model selection and results file name.
  - Chat settings: chat model, summary model, similarity threshold.
- Run panel:
  - Supports crawl+index, crawl only, or index only.
  - Optional force re-crawl.
  - Reports missing results or missing index files.
- Chat management:
  - Multiple chats per project, stored as JSON.
  - Rename/delete chats.
  - Chat messages are appended and persisted after each response.
- Query flow in UI:
  - Ensures index is on disk and loaded.
  - Calls `QueryPipeline.query()` to generate a response.

Note: `app.py` also contains non-ASCII characters (likely from icon replacement). Preserve encoding if editing.

## Pipeline Factory (`main.py`)
- `build_pipelines(config, api_key=None)`:
  - Loads env with `dotenv` and resolves `OPENAI_API_KEY`.
  - Normalizes defaults for `embedding_model` and `chat_model`.
  - Chooses embedder:
    - `openai:<model>` prefix uses `OpenAIEmbedder`.
    - Otherwise uses `HFSentenceEmbedder`.
  - Configures optional summarizer using `TextSummarizer` and a `ChatGPTModel`.
  - Creates `Crawler` with Atlas settings.
  - Returns `IngestPipeline` and `QueryPipeline`.

## Crawl Layer
### `crawl/crawler.py`
- Wraps `webcreeper.agents.atlas.Atlas`.
- Accepts start URL, allowed domains, output dir, and per-run settings.
- Uses `HTMLSaver` callback by default to store raw HTML records.

### `crawl/handlers.py`
- `HTMLSaver` validates URL and HTML and returns `{url, html, length}` for persistence.

### `webcreeper/` (Atlas crawler)
- `BaseAgent` implements:
  - Session pooling, retries/backoff, rate limiting.
  - robots.txt support (toggle).
  - Domain allow/deny with optional subdomain support.
  - URL normalization, tracking param stripping.
  - Regex allow/block lists and heuristics.
  - Disallowed reasons tracking for debugging.
- `Atlas` implements:
  - BFS/DFS crawling modes, depth-limited or full-site.
  - Deduplicates pages by text hash per run.
  - Link extraction with anchor text.
  - Writes results to `results.jsonl` and graph to `graph.json`.

## Processing Layer
### `processors/text_extractors.py`
- `TrafilaturaTextExtractor` uses `trafilatura.extract()`.
- Includes Cloudflare email de-obfuscation helper.

### `processors/text_chunkers.py`
- `SlidingTextChunker`:
  - Cleans HTML by removing nav/footer/script/etc.
  - Groups content by heading hierarchy.
  - Creates chunks using sliding window with overlap.
  - Preserves heading hierarchy and anchor links per chunk.
  - Generates deterministic chunk IDs with blake2b over URL + hierarchy + local index.

### `processors/page_processor.py`
- `SemanticPageProcessor` passes raw HTML into chunker to preserve structure.
- Adds metadata fields: hierarchy, outgoing links, deterministic id.

### `processors/text_summarizer.py`
- Uses an LLM to summarize text with a prompt template.
- Truncates by token count using `tiktoken`.

## Embedding Layer
- `HFSentenceEmbedder` uses SentenceTransformers and normalizes embeddings.
- `OpenAIEmbedder` uses OpenAI embedding models and requires `OPENAI_API_KEY`.

## Vector Storage
### `vector_index/faiss_db.py`
- FAISS wrapper with:
  - Stable 64-bit IDs based on a deterministic key.
  - IDMap2 for updates and deletes.
  - Optional index types (flat, hnsw, ivf_flat, ivf_pq).
  - Metadata saved to `metadata.meta` (pickle) and index to `embeddings.index`.

## Ingest Pipeline (`pipeline/ingest_pipeline.py`)
- Stages:
  - `extract()`: run crawler and save results.
  - `transform()`: load results, chunk, optional summarize, embed, and build metadata.
  - `load()`: add to FAISS and save index.
  - `run()`: orchestration for crawl-only, index-only, or both.
- Reads `graph.json` to build incoming link metadata.
- Debug mode writes `debug/raw_chunks.jsonl` and `debug/summaries_full.jsonl` under output dir.
- Embedding safety: splits large inputs by paragraph/sentence/char into multiple segments per chunk.

## Query Pipeline (`pipeline/query_pipeline.py`)
- Retrieval flow:
  - First-pass semantic search.
  - Optional LLM rewrite and multi-hop searches.
  - Expansion using incoming links (anchor text) and section headings.
  - Re-ranking with boost for anchor/section-derived matches.
  - Context assembly grouped by top-level headings.
  - Answerability check using LLM before final answer.
- If insufficient context, returns a fallback with up to 3 helpful URLs.

## Embed-and-Store Pipeline (`pipeline/embed_and_store.py`)
- Takes a pre-processed results file and embeds a chosen field.
- Writes FAISS index and metadata, with batching and chunk splitting.

## Storage Layer (`storage/storage_manager.py`)
Per-project folder structure under `websites_storage/<project>/`:
- `config.json`: project settings (start URL, models, thresholds, crawl settings).
- `index/`: FAISS files (`embeddings.index`, `metadata.meta`).
- `chats/`: per-chat JSON history.

Chat payload format:
```
{
  "title": "Chat 1",
  "settings": {"score_threshold": 0.5},
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

## Configuration
Project configs are JSON and passed to `build_pipelines`. Common keys:
- `start_url`, `allowed_domains`, `output_dir`, `index_dir`, `results_file`.
- Crawl settings: `crawl_entire_site`, `max_depth`, `allow_subdomains`, `respect_robots`, `rate_limit_delay`, `allowed_paths`, `blocked_paths`, `allow_url_patterns`, `block_url_patterns`, `seed_urls`.
- Model settings: `embedding_model` (HF name or `openai:<model>`), `chat_model`, optional `summary_model`.
- Retrieval: `score_threshold` (used by UI only; pipeline uses its own defaults).

Environment:
- `OPENAI_API_KEY` is required for OpenAI embeddings and chat/summarization.
- `.env` supported via `python-dotenv`.

## Docker
- `Dockerfile` builds a slim Python 3.11.7 image and runs Streamlit.
- `docker-compose.yml` maps `websites_storage` into the container.
- Note: Dockerfile sets `WORKDIR /app/Webly`, but the repo root is already the app root. If you build at repo root, `/app/Webly` may not exist unless the repo is nested; adjust if needed.

## Known Quirks and Risks
- Encoding artifacts in `README.md` and `app.py` (non-ASCII glyphs). Avoid re-encoding when editing.
- `main.py` provides a pipeline factory but not a full CLI entrypoint; README mentions CLI usage that is not implemented.
- Query pipeline uses LLM to judge answerability, which adds cost and latency.

## TODOs (from `Todo.md`)
- Navigational intent handling (return links or use site graph).
- Analytics dashboard and content gap reporting.
- Chat history export and prompt customization.

## How to Extend
- Swap embedders: implement `Embedder` interface and update config to use it.
- Swap chunker/extractor: replace `DefaultChunker` or `DefaultTextExtractor` in `IngestPipeline`.
- Add a new vector DB: implement `VectorDatabase` and update pipeline wiring.
- Add UI settings: update `app.py` to persist to project config.

## Testing and Validation
No formal tests are present. Validate by:
- Running Streamlit: `streamlit run app.py`.
- Creating a project, crawling a small site, indexing, and querying.
- Verifying `results.jsonl`, `graph.json`, and FAISS files under `websites_storage`.
