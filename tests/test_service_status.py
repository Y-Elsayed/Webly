from fastapi.testclient import TestClient

from webly.service.app import create_app


def test_status_reports_unready_project_without_api_key(tmp_path, monkeypatch):
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

    response = client.get("/v1/projects/Docs/status")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Docs"
    assert body["results_ready"] is False
    assert body["index_ready"] is False
    assert body["query_ready"] is False
    assert body["chat_ready"] is False
    assert body["capabilities"]["has_openai_api_key"] is False
    assert body["capabilities"]["uses_openai_embeddings"] is False
    assert body["capabilities"]["query_pipeline_available"] is False


def test_status_uses_runtime_status_when_available(tmp_path, monkeypatch):
    app = create_app(storage_root=str(tmp_path))
    client = TestClient(app)
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
                "query_pipeline_available": True,
            },
        },
    )

    response = client.get("/v1/projects/Docs/status")

    assert response.status_code == 200
    body = response.json()
    assert body["results_ready"] is True
    assert body["index_ready"] is True
    assert body["query_ready"] is True
    assert body["chat_ready"] is True
    assert body["capabilities"]["has_openai_api_key"] is True
