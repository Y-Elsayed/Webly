"""Run only after Core-only verification and installing API/UI extras."""

import tempfile

import streamlit
from fastapi.testclient import TestClient

from webly.service.app import create_app

assert streamlit.__version__
with tempfile.TemporaryDirectory(prefix="webly-adapter-smoke-") as storage:
    with TestClient(create_app(storage_root=storage)) as client:
        assert client.get("/healthz").status_code == 200
        assert (
            client.post(
                "/v1/projects",
                json={
                    "name": "fixture",
                    "config": {"start_url": "https://example.test"},
                },
            ).status_code
            == 201
        )
        assert client.get("/v1/projects/fixture").status_code == 200
        assert client.delete("/v1/projects/fixture").status_code in (200, 204)
print("Optional API/UI package checks passed; no adapter tests skipped.")
