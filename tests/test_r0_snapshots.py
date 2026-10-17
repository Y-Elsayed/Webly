import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from webly.project_config import ProjectConfig
from webly.query_result import QueryResult
from webly.runtime import ProjectRuntime
from webly.vector_index.faiss_db import FaissDatabase
from webly.vector_index.snapshots import SnapshotStore


def _db(segment_id: str, model: str = "model-a") -> FaissDatabase:
    db = FaissDatabase(embedding_space={
        "provider_model": model, "dimensions": 2,
        "distance": "normalized_inner_product", "embedding_text_version": "chunker-v2",
    })
    db.create(2)
    db.add([{"segment_id": segment_id, "url": "https://example.test/p", "original_text": segment_id,
             "text": segment_id, "embedding_text": segment_id, "embedding": [1, 0]}])
    return db


def test_publish_reload_rollback_and_model_compatibility(tmp_path):
    store = SnapshotStore(tmp_path / "index")
    first = _db("first")
    v1 = store.publish(first)
    pinned = FaissDatabase(str(store.validate(v1, embedding_space=first.embedding_space)),
                           embedding_space=first.embedding_space)
    v2 = store.publish(_db("second"), expected_version=v1)
    assert store.active_version() == v2
    assert pinned.search([1, 0])[0]["segment_id"] == "first"
    assert FaissDatabase(str(store.validate(v2)) ).search([1, 0])[0]["segment_id"] == "second"
    with pytest.raises(RuntimeError, match="Embedding space mismatch"):
        store.validate(v2, embedding_space=_db("other", model="model-b").embedding_space)
    store.rollback(v1, expected_version=v2, embedding_space=first.embedding_space)
    assert store.active_version() == v1


def test_failed_publication_preserves_old_active(tmp_path, monkeypatch):
    store = SnapshotStore(tmp_path / "index")
    v1 = store.publish(_db("first"))

    def fail_pointer(_version):
        raise OSError("simulated publication failure")

    monkeypatch.setattr(store, "_write_pointer", fail_pointer)
    with pytest.raises(OSError, match="simulated"):
        store.publish(_db("second"), expected_version=v1)
    assert store.active_version() == v1
    assert FaissDatabase(str(store.validate(v1))).search([1, 0])[0]["segment_id"] == "first"


def test_stale_writer_cannot_replace_new_active_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "index")
    first = store.publish(_db("first"))
    second = store.publish(_db("second"), expected_version=first)
    with pytest.raises(RuntimeError, match="Active snapshot changed"):
        store.publish(_db("stale"), expected_version=first)
    assert store.active_version() == second
    assert FaissDatabase(str(store.validate(second))).search([1, 0])[0]["segment_id"] == "second"


def test_changed_source_copy_cannot_publish(tmp_path):
    store = SnapshotStore(tmp_path / "index")
    first = store.publish(_db("first"))
    source = tmp_path / "results.jsonl"
    source.write_text('{"url":"https://example.test/p","html":"old"}\n')
    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text('{"url":"https://example.test/p","html":"new"}\n')
    with pytest.raises(RuntimeError, match="changed during snapshot copy"):
        store.publish(
            _db("second"), source_path=str(source),
            expected_source_digest=original_digest, expected_version=first,
        )
    assert store.active_version() == first


def test_concurrent_reads_during_publication_see_complete_version(tmp_path):
    store = SnapshotStore(tmp_path / "index")
    initial = store.publish(_db("first"))

    def read_many():
        seen = set()
        for _ in range(60):
            version = store.active_version()
            db = FaissDatabase(str(store.validate(version)))
            seen.add(db.search([1, 0])[0]["segment_id"])
        return seen

    with ThreadPoolExecutor(max_workers=4) as pool:
        readers = [pool.submit(read_many) for _ in range(3)]
        new_version = store.publish(_db("second"), expected_version=initial)
        seen = set().union(*(future.result() for future in readers))
    assert seen <= {"first", "second"}
    assert new_version != initial
    assert store.active_version() == new_version


def test_tampered_artifact_and_manifest_are_rejected(tmp_path):
    store = SnapshotStore(tmp_path / "index")
    version = store.publish(_db("first"))
    path = store.version_path(version)
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["segment_count"] = 2
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="count mismatch"):
        store.validate(version)


def test_runtime_request_pins_old_version_while_new_version_publishes(tmp_path):
    store = SnapshotStore(tmp_path / "index")
    old_db = _db("old")
    old_version = store.publish(old_db)
    entered = threading.Event()
    continue_query = threading.Event()

    class Ingest:
        db = FaissDatabase(embedding_space=old_db.embedding_space)

    class ChatAgent:
        vector_db = None

    class Retriever:
        chat_agent = ChatAgent()
        _bm25_ready = False

    class Query:
        chat_agent = Retriever.chat_agent
        retriever = Retriever()

        def query_result(self, *_args, **_kwargs):
            pinned_db = self.chat_agent.vector_db
            entered.set()
            assert continue_query.wait(5)
            hit = pinned_db.search([1, 0])[0]
            return QueryResult(answer=hit["original_text"], supported=True)

    class Tracker:
        def flush(self):
            pass

    cfg = ProjectConfig.from_dict(
        {"start_url": "https://example.test/p"}, output_dir=str(tmp_path), index_dir=str(store.root)
    )
    runtime = ProjectRuntime(cfg, Ingest(), Query(), Tracker())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runtime.query_result, "question")
        assert entered.wait(5)
        new_version = store.publish(_db("new"), expected_version=old_version)
        continue_query.set()
        old_result = future.result()
    assert old_result.answer == "old"
    assert old_result.trace["index_version"] == old_version
    assert runtime.query_result("question").trace["index_version"] == new_version
