from pathlib import Path

import pytest

np = pytest.importorskip("numpy", exc_type=ImportError)
FaissDatabase = pytest.importorskip("vector_index.faiss_db", exc_type=ImportError).FaissDatabase


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

    db2 = FaissDatabase()
    db2.load(str(path))
    results2 = db2.search(q, top_k=1)
    assert results2
    assert results2[0]["url"] == "https://a"
