from fastapi.testclient import TestClient

from webly.service.app import create_app


def _create_project(client: TestClient) -> None:
    response = client.post(
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
    assert response.status_code == 201


def test_chat_crud_roundtrip(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))
    _create_project(client)

    list_response = client.get("/v1/projects/Docs/chats")
    assert list_response.status_code == 200
    assert list_response.json() == {"items": []}

    put_response = client.put(
        "/v1/projects/Docs/chats/session-1",
        json={
            "settings": {"score_threshold": 0.75, "memory_reset_at": 3},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ],
        },
    )
    assert put_response.status_code == 200
    assert put_response.json() == {
        "title": "session-1",
        "settings": {"score_threshold": 0.75, "memory_reset_at": 3},
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
    }

    list_after_save = client.get("/v1/projects/Docs/chats")
    assert list_after_save.status_code == 200
    assert list_after_save.json() == {"items": ["session-1"]}

    get_response = client.get("/v1/projects/Docs/chats/session-1")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "session-1"
    assert get_response.json()["settings"]["memory_reset_at"] == 3

    delete_response = client.delete("/v1/projects/Docs/chats/session-1")
    assert delete_response.status_code == 204

    missing_after_delete = client.get("/v1/projects/Docs/chats/session-1")
    assert missing_after_delete.status_code == 404


def test_chat_put_normalizes_defaults(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))
    _create_project(client)

    response = client.put(
        "/v1/projects/Docs/chats/session-2",
        json={"messages": [{"role": "user", "content": "Only user"}]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "title": "session-2",
        "settings": {"score_threshold": 0.5, "memory_reset_at": 0},
        "messages": [{"role": "user", "content": "Only user"}],
    }


def test_chat_routes_return_404_for_missing_project_or_chat(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))

    missing_project = client.get("/v1/projects/Missing/chats")
    assert missing_project.status_code == 404

    _create_project(client)
    missing_chat = client.get("/v1/projects/Docs/chats/absent")
    assert missing_chat.status_code == 404
