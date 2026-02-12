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

### Next
- Improve overall UI quality (layout consistency, clarity of actions/states, better empty/error states)
- Add an onboarding wizard for first-time setup (env, model choice, first project)
- Add a guided install flow (step-by-step checks with clear success/failure states)
- Add quick in-app diagnostics panel (index status, last crawl stats)
- Add chat/source export from UI
- Improve error messages for crawl policy misconfiguration

### Later
- Split the large `app.py` script into modular UI components
  (`ui/projects.py`, `ui/run.py`, `ui/chat.py`, `ui/settings.py`, shared state/helpers)
- Multi-user auth and project sharing

## API Service Layer (non-UI usage)
### Done
- Core pipelines are importable and callable from Python modules

### Next
- Add a lightweight FastAPI service exposing core operations:
  - `POST /projects`
  - `POST /projects/{id}/crawl`
  - `POST /projects/{id}/index`
  - `POST /projects/{id}/query`
  - `GET /projects/{id}/status`

### Later
- Async/background jobs for long-running crawl/index tasks
- Auth/rate limiting for hosted API mode

## Crawling (`webcreeper/`, `crawl/`)
### Done
- Domain/path/pattern controls
- Robots toggle and rate-limiting support
- Link graph generation (`graph.json`)
- Crawl output persistence (`results.jsonl`)

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

### Next
- Config schema validation with defaults and better error surfacing
- Stronger chunk metadata consistency and docs
- Expand ingest tests for edge conditions

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

### Next
- Improve query understanding so retrieval can better parse user intent and reformulate searches
- Add stronger reasoning-aware retrieval steps for ambiguous or multi-part questions
- Improve route-decision quality so standalone questions are less likely to be treated as follow-ups
- Improve "Read more" precision to prioritize links most relevant to the current question only
- Source citation quality improvements
- Query evaluation harness (gold questions + metrics)
- Retrieval cache for repeated queries

### Later
- Cross-encoder reranking
- Feedback-aware retrieval improvements

## Embeddings and Vector Store (`embedder/`, `vector_index/`)
### Done
- OpenAI-focused API-backed embedding/chat integration
- FAISS backend with metadata persistence
- Deterministic ID behavior for stored records

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

### Next
- Improve documentation depth for both developers and non-technical users
- Add a dedicated non-technical user guide (what to click, what to expect, common errors)
- Add screenshot/GIF walkthroughs (project creation -> crawl/index -> chat)
- Add troubleshooting docs for common setup/runtime failures

### Later
- Publish versioned docs site
- Add video walkthroughs and template use-case playbooks
