from fastapi.testclient import TestClient

from webly.service.app import create_app


def test_validation_errors_are_returned_as_400_with_standard_payload(tmp_path):
    client = TestClient(create_app(storage_root=str(tmp_path)))

    response = client.post("/v1/projects", json={"name": "Docs"})

    assert response.status_code == 400
    assert "detail" in response.json()


def test_capture_policy_mismatch_returns_actionable_nonretryable_conflict(tmp_path):
    from webly.contracts import RunPolicyMismatch

    app = create_app(storage_root=str(tmp_path))

    @app.get("/test-policy-error")
    def mismatch():
        raise RunPolicyMismatch(["max_depth", "allowed_paths"])

    response = TestClient(app).get("/test-policy-error")
    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "run_policy_mismatch" and payload["retryable"] is False
    assert payload["changed_fields"] == ["allowed_paths", "max_depth"]
