from fastapi.testclient import TestClient

from webly.service.app import create_app


def test_ingest_endpoint_runs_runtime_ingest(tmp_path, monkeypatch):
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
        "run_ingest",
        lambda project, mode="both", force_crawl=False: {
            "project": project,
            "mode": mode,
            "force_crawl": force_crawl,
            "indexed": True,
        },
    )

    response = client.post(
        "/v1/projects/Docs/ingest",
        json={"mode": "index_only", "force_crawl": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"] == {
        "project": "Docs",
        "mode": "index_only",
        "force_crawl": True,
        "indexed": True,
    }


def test_ingest_endpoint_returns_400_for_invalid_mode(tmp_path, monkeypatch):
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

    def _raise_invalid(_project, mode="both", force_crawl=False):
        raise ValueError(f"Invalid mode: {mode}")

    monkeypatch.setattr(app.state.container.runtime_service, "run_ingest", _raise_invalid)

    response = client.post("/v1/projects/Docs/ingest", json={"mode": "bad-mode"})

    assert response.status_code == 400


def test_ingest_endpoint_returns_404_for_missing_project(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))

    response = client.post("/v1/projects/Missing/ingest", json={"mode": "both"})

    assert response.status_code == 404
