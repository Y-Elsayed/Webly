# Webly

![CI](https://github.com/Y-Elsayed/webly/actions/workflows/ci.yml/badge.svg)

Webly is a modular website-to-RAG framework. It crawls websites, extracts and chunks content, embeds it, stores vectors, and provides a chat/search interface over that knowledge.

## What It Does
- Crawl websites with policy controls (domains, depth, robots, URL filters)
- Build `results.jsonl` and a site `graph.json`
- Chunk and optionally summarize content
- Embed content and index it in FAISS
- Retrieve, rerank, and answer user questions in Streamlit

## Architecture
- `app.py`: Streamlit UI and project/chat management
- `main.py`: pipeline factory (`build_pipelines`)
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

## Configuration
Create/update a project in the UI, or use a config with keys like:
- `start_url`, `allowed_domains`
- `output_dir`, `index_dir`, `results_file`
- `embedding_model`, `chat_model`, optional `summary_model`
- crawl controls (`max_depth`, `respect_robots`, `allow_url_patterns`, etc.)

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

## Community and Policies
- Contributing: `CONTRIBUTING.md`
- Security: `SECURITY.md`
- Code of Conduct: `CODE_OF_CONDUCT.md`

## Contact
[Yassin Ali](mailto:yelsayed003@gmail.com)
