from fastapi.testclient import TestClient

from webly.query_result import QueryResult, SourceRef
from webly.service.app import create_app


class _DummyRuntime:
    def query_result(self, question: str, *, retry_on_empty: bool = False, memory_context: str = "") -> QueryResult:
        return QueryResult(
            answer=f"answer:{question}",
            supported=True,
            sources=[SourceRef(chunk_id="chunk-1", url="https://example.com/docs", section="Docs")],
            trace={"retry_on_empty": retry_on_empty, "memory_context": memory_context},
        )


def test_query_endpoint_returns_structured_query_result(tmp_path, monkeypatch):
    app = create_app(storage_root=str(tmp_path))
    client = TestClient(app)
    client.post(
        "/v1/projects",
        json={
            "name": "Docs",
            "config": {
                "start_url": "https://example.com/docs",
                "allowed_domains": ["example.com"],
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            },
        },
    )

    monkeypatch.setattr(
        app.state.container.runtime_service,
        "build_project_runtime",
        lambda _project: _DummyRuntime(),
    )
    monkeypatch.setattr(
        app.state.container.runtime_service,
        "status",
        lambda _project: {
            "config": app.state.container.project_service.get_project("Docs"),
            "paths": app.state.container.project_service.projects.get_paths("Docs"),
            "results_ready": True,
            "index_ready": True,
            "query_ready": True,
            "chat_ready": True,
            "capabilities": {
                "has_openai_api_key": True,
                "uses_openai_embeddings": False,
                "uses_summary_model": False,
                "requires_openai_for_ingest": False,
                "requires_openai_for_query": True,
                "ingest_pipeline_available": True,
                "query_pipeline_available": True,
                "blockers": [],
            },
        },
    )

    response = client.post(
        "/v1/projects/Docs/query",
        json={
            "question": "How does this work?",
            "memory_context": "Earlier context",
            "retry_on_empty": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "answer:How does this work?"
    assert body["supported"] is True
    assert body["sources"] == [
        {"chunk_id": "chunk-1", "url": "https://example.com/docs", "section": "Docs"}
    ]
    assert body["trace"]["retry_on_empty"] is True
    assert body["trace"]["memory_context"] == "Earlier context"


def test_query_endpoint_returns_404_for_missing_project(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))

    response = client.post("/v1/projects/Missing/query", json={"question": "hello"})

    assert response.status_code == 404


def test_query_endpoint_returns_503_when_query_runtime_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(create_app(storage_root=str(tmp_path)))
    create = client.post(
        "/v1/projects",
        json={
            "name": "Docs",
            "config": {
                "start_url": "https://example.com/docs",
                "allowed_domains": ["example.com"],
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            },
        },
    )
    assert create.status_code == 201

    response = client.post("/v1/projects/Docs/query", json={"question": "hello"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": "OPENAI_API_KEY is required for query and chat responses."
    }
