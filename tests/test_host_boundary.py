import io
import logging

import pytest
from test_core_v2 import make_runtime

from scripts.worker_example import SQLiteEvents
from webcreeper.creeper_core.utils import UnicodeStreamHandler
from webly.contracts import ArtifactError, OperationContext


def test_durable_event_delivery_deduplicates_and_rejects_changed_payload(tmp_path):
    path = tmp_path / "events.sqlite"
    event = {"operation_id": "op", "sequence": 1, "kind": "progress"}
    sink = SQLiteEvents(path)
    sink(event)
    sink(event)
    sink.close()
    reopened = SQLiteEvents(path)
    try:
        reopened(event)
        assert reopened.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        with pytest.raises(ValueError):
            reopened({**event, "kind": "changed"})
    finally:
        reopened.close()


def test_query_artifact_error_masks_details_and_retains_operation(tmp_path, monkeypatch):
    with make_runtime(tmp_path / "core") as runtime:

        def fail():
            raise OSError("secret-key-and-private-host-path")

        monkeypatch.setattr(type(runtime), "ensure_index_loaded", lambda _self: fail())
        context = OperationContext(operation_id="host-operation")
        with pytest.raises(ArtifactError) as caught:
            runtime.query_result("Question?", context=context)
        assert caught.value.operation_id == "host-operation"
        assert "secret" not in str(caught.value)


def test_unicode_crawl_diagnostics_survive_legacy_terminal_encoding():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    handler = UnicodeStreamHandler(stream)
    handler.emit(logging.LogRecord("crawler", logging.INFO, "", 0, "Arabic: \u0645\u0631\u062d\u0628\u0627", (), None))
    handler.flush()
    assert b"Arabic: \\u0645" in raw.getvalue()
