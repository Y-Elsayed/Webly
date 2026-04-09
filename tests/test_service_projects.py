from fastapi.testclient import TestClient

from webly.service.app import create_app


def test_projects_crud_roundtrip(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))

    response = client.get("/v1/projects")
    assert response.status_code == 200
    assert response.json() == {"items": []}

    create_response = client.post(
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
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["name"] == "Docs"
    assert body["config"]["start_url"] == "https://example.com/docs"
    assert body["config"]["output_dir"].endswith("Docs")
    assert body["paths"]["index"].endswith("Docs\\index") or body["paths"]["index"].endswith("Docs/index")

    get_response = client.get("/v1/projects/Docs")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Docs"

    patch_response = client.patch(
        "/v1/projects/Docs",
        json={"config": {"max_depth": 7, "score_threshold": 0.75}},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["config"]["max_depth"] == 7
    assert patch_response.json()["config"]["score_threshold"] == 0.75

    delete_response = client.delete("/v1/projects/Docs")
    assert delete_response.status_code == 204

    missing_response = client.get("/v1/projects/Docs")
    assert missing_response.status_code == 404


def test_create_project_conflict_returns_409(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))
    payload = {
        "name": "Docs",
        "config": {
            "start_url": "https://example.com/docs",
            "allowed_domains": ["example.com"],
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        },
    }
    assert client.post("/v1/projects", json=payload).status_code == 201
    conflict = client.post("/v1/projects", json=payload)
    assert conflict.status_code == 409
