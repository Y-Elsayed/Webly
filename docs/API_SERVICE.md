# API Service

Webly now includes a local FastAPI service built on top of the same runtime and repository layer used by the Streamlit app.

This service is intentionally:
- single-tenant
- filesystem-backed
- project-folder oriented
- local-first, not a hosted multi-user backend

## Install

```bash
pip install .[api]
```

## Run

```bash
uvicorn webly.service.app:app --host 127.0.0.1 --port 8000
```

Optional storage root override:

```bash
WEBLY_STORAGE_ROOT=./websites_storage uvicorn webly.service.app:app --host 127.0.0.1 --port 8000
```

## Current Endpoints

- `GET /healthz`
- `GET /v1/projects`
- `POST /v1/projects`
- `GET /v1/projects/{project}`
- `PATCH /v1/projects/{project}`
- `DELETE /v1/projects/{project}`
- `GET /v1/projects/{project}/status`
- `POST /v1/projects/{project}/query`
- `POST /v1/projects/{project}/ingest`
- `GET /v1/projects/{project}/chats`
- `GET /v1/projects/{project}/chats/{chat}`
- `PUT /v1/projects/{project}/chats/{chat}`
- `DELETE /v1/projects/{project}/chats/{chat}`

## Example: Create a Project

```bash
curl -X POST http://127.0.0.1:8000/v1/projects ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Docs\",\"config\":{\"start_url\":\"https://example.com/docs\",\"allowed_domains\":[\"example.com\"],\"embedding_model\":\"sentence-transformers/all-MiniLM-L6-v2\"}}"
```

## Example: Query a Project

```bash
curl -X POST http://127.0.0.1:8000/v1/projects/Docs/query ^
  -H "Content-Type: application/json" ^
  -d "{\"question\":\"How does authentication work?\",\"memory_context\":\"\"}"
```

Response shape:

```json
{
  "answer": "Grounded answer text",
  "supported": true,
  "sources": [
    {
      "chunk_id": "chunk-1",
      "url": "https://example.com/docs/auth",
      "section": "Authentication"
    }
  ],
  "trace": {}
}
```

## Example: Ingest a Project

```bash
curl -X POST http://127.0.0.1:8000/v1/projects/Docs/ingest ^
  -H "Content-Type: application/json" ^
  -d "{\"mode\":\"both\",\"force_crawl\":false}"
```

## Example: Persist a Chat

```bash
curl -X PUT http://127.0.0.1:8000/v1/projects/Docs/chats/session-1 ^
  -H "Content-Type: application/json" ^
  -d "{\"settings\":{\"score_threshold\":0.5,\"memory_reset_at\":0},\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
```

The chat payload matches Webly's existing filesystem chat schema:
- `title`
- `settings.score_threshold`
- `settings.memory_reset_at`
- `messages[]` with `role` and `content`

## Notes

- `POST /query` uses the structured `QueryResult` contract rather than the legacy string-only response.
- `GET /status` is lightweight and does not force a full runtime bootstrap just to report readiness.
- `POST /ingest` is currently synchronous.
- The service does not currently implement auth, multi-tenant workspaces, background workers, or streaming responses.
