# Roadmap

This roadmap is organized by Webly components and split into:
- `Done`: implemented in the current codebase
- `Next`: high-priority follow-ups
- `Later`: larger or optional upgrades

## UI and Developer Experience (`app.py`, docs)
### Done
- Streamlit project management flow (create/select/delete projects)
- Run modes (`crawl_only`, `index_only`, `both`)
- Multi-chat management with persisted histories
- Key validation flow for OpenAI API keys
- Dockerized app run path
- Retrieval mode controls in UI (`builder` / `classic`)
- Memory window control (`leave_last_k`) and builder rounds setting in UI
- UI modules split under `webly/ui/` with runtime-backed project rebuild flow
- Typed config/runtime bootstrap separated from Streamlit-specific state

### Next
- Improve overall UI quality (layout consistency, clarity of actions/states, better empty/error states)
- Add an onboarding wizard for first-time setup (env, model choice, first project)
- Add a guided install flow (step-by-step checks with clear success/failure states)
- Add quick in-app diagnostics panel (index status, last crawl stats)
- Add chat/source export from UI
- Improve error messages for crawl policy misconfiguration

### Later
- Multi-user auth and project sharing

## API Service Layer (non-UI usage)
### Done
- Core pipelines are importable and callable from Python modules
- Typed runtime/config bootstrap (`ProjectConfig`, `ProjectRuntime`, `build_runtime`)
- Local FastAPI service package under `webly/service/`
- Project CRUD endpoints
- Query endpoint returning structured results (`answer`, `supported`, `sources`, `trace`)
- Lightweight project status endpoint
- Synchronous ingest endpoint
- Chat persistence endpoints backed by the existing filesystem repository layer

### Next
- Global exception normalization and consistent error payloads
- Better service docs and OpenAPI examples
- Optional in-memory job registry if ingest should stop blocking request threads

### Later
- Async/background jobs for long-running crawl/index tasks
- Auth/rate limiting for hosted API mode
- Streaming query responses

## Crawling (`webcreeper/`, `crawl/`)
### Done
- Domain/path/pattern controls
- Robots toggle and rate-limiting support
- Link graph generation (`graph.json`)
- Crawl output persistence (`results.jsonl`)
- Crawler adapter now retains Atlas state for diagnostics/report access

### Next
- Better URL canonicalization edge cases
- Crawl diagnostics report surfaced in UI
- More crawler policy tests

### Later
- Async crawling with bounded concurrency
- Resume support (persist frontier/visited)
- Optional JS rendering for JS-heavy sites

## Processing and Ingest (`processors/`, `pipeline/ingest_pipeline.py`)
### Done
- HTML extraction + structural chunking
- Optional summarization path
- Segment-safe embedding preparation
- Ingest orchestration for crawl/index modes
- Shared embedding text segmentation reused across ingest codepaths

### Next
- Stronger chunk metadata consistency and docs
- Expand ingest tests for edge conditions
- Continue decomposing `IngestPipeline` into smaller collaborators
- Extract crawl output and `results.jsonl` loading into a dedicated results reader
- Extract `graph.json` loading and graph metadata enrichment into dedicated graph helpers
- Extract checkpoint read/write and resume decisions into a dedicated checkpoint store
- Extract page/chunk/embedding preparation into a dedicated ingest preparation helper
- Keep `IngestPipeline.run()` as the compatibility orchestrator while moving internal responsibilities out

Planned ingest decomposition order:
1. Results reader and graph enricher
2. `IngestPipeline` rewiring to use those helpers
3. Checkpoint store extraction
4. Embedding preparation extraction
5. Final `IngestPipeline` cleanup as a thin coordinator

### Later
- Pluggable extractors (additional parser backends)
- Language-aware chunking
- Near-duplicate chunk deduplication

## Retrieval and Chat (`pipeline/query_pipeline.py`, `chatbot/`)
### Done
- Vector retrieval
- Hybrid retrieval path (BM25 + vector)
- Graph/section expansion and reranking
- Answerability/fallback behavior
- Builder retrieval mode with LLM-driven concept extraction and follow-up planning
- Initial query routing modes (`transform_only`, `retrieve_followup`, `retrieve_new`)
- Best-effort responses with concept-oriented "Read more" links
- Typed query results plus explicit sources/trace for reuse outside Streamlit
- Configured `score_threshold` now applies to vector retrieval
- Query evaluation harness with golden query cases covering supported, best-effort, and hard-fallback paths

### Next
- Improve query understanding so retrieval can better parse user intent and reformulate searches
- Add stronger reasoning-aware retrieval steps for ambiguous or multi-part questions
- Improve route-decision quality so standalone questions are less likely to be treated as follow-ups
- Improve "Read more" precision to prioritize links most relevant to the current question only
- Source citation quality improvements
- Extend the query evaluation harness with metrics-oriented cases and broader retrieval regression coverage
- Retrieval cache for repeated queries
- Decompose the current `QueryPipeline` god class into smaller retrieval/context components

### Later
- Cross-encoder reranking
- Feedback-aware retrieval improvements

## Embeddings and Vector Store (`embedder/`, `vector_index/`)
### Done
- OpenAI-focused API-backed embedding/chat integration
- FAISS backend with metadata persistence
- Deterministic ID behavior for stored records
- Runtime/service-level index readiness checks

### Next
- Explicit migration/version metadata for index files
- Better index health checks in runtime flow
- Add provider wrappers for additional model APIs (beyond OpenAI)

### Later
- Expand first-class support for open-source/local model providers
  (embedding and chat wrappers)
- Qdrant adapter
- Milvus adapter
- Backend comparison benchmarks (latency/recall/cost)

## Storage and Persistence (`storage/`, `websites_storage/`)
### Done
- Per-project config storage
- Per-chat persisted history payloads
- Repository-backed project/chat persistence layer
- Project folder conventions for results/index/chats
- BOM-safe JSON reads/writes for project config and chat files

### Next
- Validation and migration handling for old config/chat schemas
- Optional backup/export command for project snapshots

### Later
- Cross-project search/federated query mode

## Quality, CI, and OSS Operations
### Done
- CI workflow with Ruff + pytest
- Apache-2.0 license + NOTICE
- Contributor/security/conduct docs
- Clean lint baseline and passing tests

### Next
- Add issue templates and PR template
- Add `CODEOWNERS`
- Add `CHANGELOG.md` for release history
- Enable branch protection (require CI green)

### Later
- Release automation (tag + notes workflow)
- Optional coverage reporting in CI

## Documentation and Adoption
### Done
- Core README with quick-start and development commands
- API service documentation with endpoint examples

### Next
- Improve documentation depth for both developers and non-technical users
- Add a dedicated non-technical user guide (what to click, what to expect, common errors)
- Add screenshot/GIF walkthroughs (project creation -> crawl/index -> chat)
- Add troubleshooting docs for common setup/runtime failures

### Later
- Publish versioned docs site
- Add video walkthroughs and template use-case playbooks
