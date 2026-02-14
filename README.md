# Webly

![CI](https://github.com/Y-Elsayed/webly/actions/workflows/ci.yml/badge.svg)
![Webly Logo](./webly-logo.png)

Webly is a modular website-to-RAG framework. It crawls websites, extracts and chunks content, embeds it, stores vectors, and provides a chat/search interface over that knowledge.

Current provider note:
- API-backed model integration is currently OpenAI-focused (`OPENAI_API_KEY`).

Grounding policy:
- Answers are intended to be grounded in retrieved website context.
- If coverage is weak or unrelated, Webly should return a fallback instead of using external knowledge.

User guide:
- GUI usage guide: `docs/USER_GUIDE.md`

## What It Does
- Crawl websites with policy controls (domains, depth, robots, URL filters)
- Build `results.jsonl` and a site `graph.json`
- Chunk and optionally summarize content
- Embed content and index it in FAISS
- Retrieve, rerank, and answer user questions in Streamlit
- Run an agentic builder retrieval mode with concept coverage checks and follow-up retrieval rounds

## Architecture
- `app.py`: Streamlit UI and project/chat management
- `main.py`: pipeline factory (`build_pipelines`)
- `chatbot/prompts/`: prompt files used by retrieval/chat agents
- `crawl/` + `webcreeper/`: crawling
- `processors/`: extraction, chunking, summarization
- `embedder/`: embedding backends
- `pipeline/`: ingest and query orchestration
- `vector_index/`: FAISS wrapper
- `storage/`: project/chat persistence

## Quick Start
Python `3.11.7` is recommended.

```bash
pip install -r requirements.txt
cp .env.example .env
# set OPENAI_API_KEY in .env
streamlit run app.py
```

Windows PowerShell alternative:
```powershell
Copy-Item .env.example .env
```

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
- `retrieval_mode` (`builder` or `classic`)
- `builder_max_rounds` (follow-up retrieval rounds for builder mode)
- `leave_last_k` (limit memory to the last K question/answer pairs; `0` keeps default behavior)
- crawl controls (`max_depth`, `respect_robots`, `allow_url_patterns`, etc.)

Current defaults:
- `retrieval_mode = "builder"`
- `builder_max_rounds = 1`
- `leave_last_k = 2`

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
Key near-term focus includes better user-intent parsing and reasoning-aware retrieval quality.

## Community and Policies
- Contributing: `CONTRIBUTING.md`
- Security: `SECURITY.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`

## Contact
[Yassin Ali](mailto:yelsayed003@gmail.com)
