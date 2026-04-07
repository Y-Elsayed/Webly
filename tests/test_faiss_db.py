import json
import logging
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


def test_missing_version_warns_but_loads(tmp_path: Path, caplog):
    path = _save_one_record_index(tmp_path)
    meta_path = path / "metadata.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    del data["config"]["index_version"]
    meta_path.write_text(json.dumps(data), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        db = FaissDatabase(str(path))

    assert db.index is not None
    assert any("index_version" in record.message for record in caplog.records)
