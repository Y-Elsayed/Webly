from fastapi.testclient import TestClient

from webly.service.app import create_app


def test_validation_errors_are_returned_as_400_with_standard_payload(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))

    response = client.post("/v1/projects", json={"name": "Docs"})

    assert response.status_code == 400
    assert "detail" in response.json()
