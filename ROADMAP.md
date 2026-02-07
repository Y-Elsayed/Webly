# Webly + WebCreeper Roadmap

This roadmap lists improvements by component so contributors can pick a focused area.

## WebCreeper (Crawler)
### Now (Good First Issues)
1. Unit tests for crawler policies
2. Better URL canonicalization (trailing slashes, query ordering, tracking params)
3. Crawl error reporting per URL (timeout, robots blocked, non-HTML)

### Next (Medium Effort)
1. Async crawling (httpx or aiohttp + bounded concurrency)
2. Robots crawl-delay support
3. Resume support (persist frontier + visited)

### Later (Advanced / Big Features)
1. JS rendering (Playwright/Chromium optional pipeline)
2. Priority crawl queue (BFS/DFS/priority)
3. Content-type extraction (PDFs/docs)

### Non-Goals (For Now)
- Full web-scale crawling
- Distributed crawling across multiple workers

## Retrieval (Query Pipeline)
### Now
1. Hybrid search (BM25 + vector)
2. Optional cross-encoder reranking
3. Better citations with deterministic source mapping

### Next
1. Retrieval evaluation harness (gold QA + metrics)
2. Caching for query embeddings and retrieval results

### Later
1. Learnable reranking and feedback loops
2. Multi-index retrieval (per section, per doc type)

## Ingest / Processing
### Now
1. Config validation (typed schema with defaults)
2. Cleaner chunk metadata and stable chunk IDs

### Next
1. Pluggable extractors (Readability, boilerpy3)
2. Optional language detection + language-specific chunking

### Later
1. Dedup at chunk level (near-duplicate detection)

## Storage / Vector DB
### Now
1. Qdrant adapter
2. Metadata-only export (JSONL)

### Next
1. Milvus adapter
2. Vector DB benchmarks (speed, recall)

## UI / App
### Now
1. Split `app.py` into smaller modules
2. Export chats and sources

### Next
1. Multi-user auth
2. Project sharing / permissions

## Docs / DevEx
### Now
1. Minimal examples (single page, seed URLs)
2. Add badges and versioning notes

### Next
1. Release notes + changelog
2. Contribution labels for issues
