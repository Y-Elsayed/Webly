# R0 local engine runbook

R0 is a local, file-backed engine. It does not provide hosted authentication, safe public-URL crawling, billing, structured critical-fact approval, or a customer quality claim. Use only trusted/approved sources and test credentials. Do not point these commands at production data.

## Install and verify

From the repository root, with Python 3.11 or 3.12 and a fresh virtual environment:

```sh
git submodule update --init --recursive
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[api,ui,dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m pip wheel . --no-deps -w /tmp/webly-wheels
```

Install the optional `hf` extra as well (`pip install -e '.[api,ui,dev,hf]'`) when using local sentence-transformer embeddings; it is deliberately omitted from the minimal test install because it downloads large model packages. The main pytest configuration includes only `tests/`; the pinned crawler submodule has a live-DNS test and is not part of the offline R0 gate. The old `.venv` in this checkout lacks pytest/Ruff. An independent Python 3.11 installation was used for the recorded results in `PROGRESS.md`. Set a **test** `OPENAI_API_KEY` only for optional live chat; deterministic tests do not use paid APIs. The local API can start with `python3 -m uvicorn webly.service.app:app --reload` if the API extra is installed. The CLI/UI remain available through existing package entry points. Do not expose this local API publicly: R1 authentication and network controls do not exist.

## Existing index migration: rebuild, never relabel

Legacy root-level `embeddings.index` and `metadata.json` were keyed by URL in affected builds. A single URL may contain multiple vectors while its metadata map points to only one chunk. There is no safe general metadata-only conversion, so version 1 or unversioned artifacts are rejected. The R0 index version is 2 and published as `index/versions/<version>/` with `index/active.json`. The old root-level files are left untouched but never queried.

1. Stop local queries and back up the complete project directory, especially config, crawl results, old index, chat history, and any embedding cache. Record the embedding model and source approval. Never delete the backup to make a check pass.
2. Confirm `results.jsonl` (or configured results file) contains original `url` and `html` for every required page. The rebuild requires original HTML; summaries or old vectors are insufficient. If absent, recrawl only trusted/approved public sources with `mode="both", force_crawl=True`; R1 crawler SSRF defenses are not present.
3. Rebuild from saved HTML using the local API `POST /v1/projects/{name}/ingest` with JSON `{"mode":"index_only"}` or `runtime.run_ingest(mode="index_only")`. Keep embedding model/settings the same unless intentionally changing the embedding space. Ingest serializes per project and refuses to publish if the results file changes during the build or a required record fails.
4. Check project status, inspect `active.json` and the manifest under `versions/<version>/`, run representative queries, and verify distinct same-page segment IDs and exact original-text citations. A changed model/dimension/chunker contract is rejected at load rather than silently reused.
5. If a newly published version is wrong, stop ingestion and call `SnapshotStore(index_dir).rollback(previous_version, expected_version=current_version, embedding_space=expected_space)`. Rollback validates the retained version before atomically changing the pointer. If this is the first R0 build and no previous immutable snapshot exists, restore the backup or rebuild again; the legacy index cannot be activated as an R0 snapshot.

Publication keeps old complete versions; no automatic garbage collection runs, so operators must plan disk capacity. Never manually delete an active or possibly pinned version. Pointer and artifact checksums detect accidental corruption, not malicious filesystem tampering. Local locks and atomic rename assume one shared local filesystem; distributed/object-store publication belongs to R1.

## Failure handling

- A crawl interrupted after opening its results file leaves `.crawl_incomplete`; the next `both` run recrawls instead of indexing partial content.
- Embedding, validation, checksum, or pointer publication failure leaves the prior active version in place. Investigate the error and retry from the saved input; do not edit metadata to bypass validation.
- A query pins an active version at admission. A concurrent publication may give the next query the new version, but an in-flight query finishes on its old complete FAISS bundle. Query traces include `index_version`.
- A missing or incompatible active version is an explicit service failure. Rebuild or roll back; do not copy legacy files into `versions/`.
