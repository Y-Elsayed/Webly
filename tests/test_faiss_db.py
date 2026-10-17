import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy", exc_type=ImportError)
faiss_db_mod = pytest.importorskip("webly.vector_index.faiss_db", exc_type=ImportError)
FaissDatabase = faiss_db_mod.FaissDatabase
INDEX_VERSION = faiss_db_mod.INDEX_VERSION


def test_faiss_add_search_save_load(tmp_path: Path):
    db = FaissDatabase()
    db.create(dim=4)

    records = [
        {"id": "a", "url": "https://a", "text": "hello", "embedding": [1, 0, 0, 0]},
        {"id": "b", "url": "https://b", "text": "world", "embedding": [0, 1, 0, 0]},
    ]
    db.add(records)

    q = np.array([1, 0, 0, 0], dtype="float32").tolist()
    results = db.search(q, top_k=1)
    assert results
    assert results[0]["url"] == "https://a"

    path = tmp_path / "index"
    db.save(str(path))
    assert (path / "metadata.json").is_file()
    assert not (path / "metadata.meta").exists()

    db2 = FaissDatabase()
    db2.load(str(path))
    results2 = db2.search(q, top_k=1)
    assert results2
    assert results2[0]["url"] == "https://a"


def _save_one_record_index(tmp_path: Path) -> Path:
    """Helper: create a minimal index with one record, return the index dir."""
    db = FaissDatabase()
    db.create(dim=4)
    db.add([{"id": "a", "url": "https://a", "text": "hi", "embedding": [1, 0, 0, 0]}])
    path = tmp_path / "index"
    db.save(str(path))
    return path


def test_index_version_present_in_saved_metadata(tmp_path: Path):
    path = _save_one_record_index(tmp_path)
    data = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    assert data["config"]["index_version"] == INDEX_VERSION


def test_index_version_mismatch_raises_runtime_error(tmp_path: Path):
    path = _save_one_record_index(tmp_path)
    meta_path = path / "metadata.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data["config"]["index_version"] = 99
    meta_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(RuntimeError, match="version mismatch"):
        FaissDatabase(str(path))


def test_missing_version_is_rejected_for_rebuild(tmp_path: Path):
    path = _save_one_record_index(tmp_path)
    meta_path = path / "metadata.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    del data["config"]["index_version"]
    meta_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(RuntimeError, match="rebuild required"):
        FaissDatabase(str(path))


def test_same_page_segments_keep_distinct_evidence_after_reload(tmp_path: Path):
    db = FaissDatabase()
    db.create(2)
    db.add([
        {"id": "segment-a", "url": "https://a/page", "original_text": "Fee is 10", "embedding": [1, 0]},
        {"id": "segment-b", "url": "https://a/page", "original_text": "Deadline is June", "embedding": [0, 1]},
    ])
    assert {hit["segment_id"] for hit in db.search([1, 0], 2)} == {"segment-a", "segment-b"}
    path = tmp_path / "index"
    db.save(str(path))
    loaded = FaissDatabase(str(path))
    assert {hit["segment_id"]: hit["original_text"] for hit in loaded.search([1, 0], 2)} == {
        "segment-a": "Fee is 10", "segment-b": "Deadline is June"
    }
    assert len({hit["vector_id"] for hit in loaded.search([1, 0], 2)}) == 2


def test_duplicate_and_collision_are_rejected(tmp_path: Path, monkeypatch):
    db = FaissDatabase()
    db.create(2)
    record = {"id": "a", "embedding": [1, 0]}
    with pytest.raises(ValueError, match="Duplicate"):
        db.add([record, record])
    monkeypatch.setattr(db, "_id64_from_key", lambda _key: np.int64(5))
    with pytest.raises(ValueError, match="collision"):
        db.add([record, {"id": "b", "embedding": [0, 1]}])
