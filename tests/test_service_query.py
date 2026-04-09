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
