# Webly

![CI](https://github.com/Y-Elsayed/webly/actions/workflows/ci.yml/badge.svg)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Y-Elsayed/Webly)
![Webly Logo](./webly-logo.png)

Webly is a modular website-to-RAG framework. It crawls websites, extracts and chunks content, embeds it, stores vectors, and provides a chat/search interface over that knowledge.

Current provider note:
- API-backed model integration is currently OpenAI-focused (`OPENAI_API_KEY`).

Grounding policy:
- Answers are intended to be grounded in retrieved website context.
- If coverage is weak or unrelated, Webly should return a fallback instead of using external knowledge.

User guide:
- GUI usage guide: `docs/USER_GUIDE.md`
- API service guide: `docs/API_SERVICE.md`

## What It Does
- Crawl websites with policy controls (domains, depth, robots, URL filters)
- Build `results.jsonl` and a site `graph.json`
- Chunk and optionally summarize content
- Embed content and index it in FAISS
- Retrieve, rerank, and answer user questions in Streamlit
- Run an agentic builder retrieval mode with concept coverage checks and follow-up retrieval rounds

## Architecture
- `webly/project_config.py`: typed project config normalization + validation
- `webly/runtime.py`: runtime bootstrap and index/query lifecycle (`build_runtime`)
- `webly/framework.py`: compatibility factory (`build_pipelines`)
- `webly/chatbot/prompts/`: prompt files used by retrieval/chat agents
- `webly/crawl/` + `webly/webcreeper/`: crawling runtime
- `webly/processors/`: extraction, chunking, summarization
- `webly/embedder/`: embedding backends
- `webly/pipeline/`: ingest and query orchestration
- `webly/vector_index/`: FAISS wrapper
- `webly/storage/`: repository-backed project/chat persistence

## Framework Quick Start
Python `3.11.7` is recommended.

```bash
pip install .
cp .env.example .env
# set OPENAI_API_KEY in .env
```

Optional extras:
```bash
pip install .[ui]
pip install .[api]
pip install .[hf]
pip install .[all]
```

Use:
- `.[ui]` for the Streamlit app
- `.[api]` for the local FastAPI service
- `.[hf]` for local Hugging Face embeddings
- `.[all]` for both

Minimal framework usage:
```python
from webly import build_runtime

runtime = build_runtime({
    "start_url": "https://example.com/docs",
    "output_dir": "./data/example",
    "index_dir": "./data/example/index",
})

runtime.run_ingest(mode="both")
answer = runtime.query("What does this site document?")
result = runtime.query_result("What does this site document?")
```

Windows PowerShell alternative for `.env`:
```powershell
Copy-Item .env.example .env
```

## Streamlit App
```bash
pip install .[ui]
streamlit run app.py
```

## API Service
```bash
pip install .[api]
uvicorn webly.service.app:app --host 127.0.0.1 --port 8000
```

Current local service endpoints:
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

See `docs/API_SERVICE.md` for request and response examples.

## Run with Docker
```bash
docker compose up --build -d
```

Open in browser:
- `http://localhost:8501`

Note:
- Container logs may show `http://0.0.0.0:8501`. That is expected inside Docker.
- From your machine, always use `http://localhost:8501`.

## Configuration
Create/update a project in the UI, or use a config with keys like:
- `start_url`, `allowed_domains`
- `output_dir`, `index_dir`, `results_file`
- `embedding_model`, `chat_model`, optional `summary_model`
- Framework default: `embedding_model = "openai:text-embedding-3-small"`
- `retrieval_mode` (`builder` or `classic`)
- `builder_max_rounds` (follow-up retrieval rounds for builder mode)
- `leave_last_k` (limit memory to the last K question/answer pairs; `0` keeps default behavior)
- crawl controls (`max_depth`, `respect_robots`, `allow_url_patterns`, etc.)

Current defaults:
- `retrieval_mode = "builder"`
- `builder_max_rounds = 1`
- `leave_last_k = 2`
- `score_threshold = 0.5` for vector similarity filtering

## Development
```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

## Contributing
See `CONTRIBUTING.md`.

## Roadmap (High Level)
See `ROADMAP.md` for a component-by-component plan with `Done`, `Next`, and `Later`.
Key near-term focus includes further retrieval decomposition, evaluation, and service hardening.

## Community and Policies
- Contributing: `CONTRIBUTING.md`
- Security: `SECURITY.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`

## Contact
[Yassin Ali](mailto:yelsayed003@gmail.com)
