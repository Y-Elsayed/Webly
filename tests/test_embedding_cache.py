from pathlib import Path

import pytest

from webly.embedder.embedding_cache import EmbeddingCache


def test_put_and_get_roundtrip(tmp_path: Path):
    cache = EmbeddingCache(str(tmp_path / ".embedding_cache.db"))
    key = EmbeddingCache.make_key("hello world", "text-embedding-3-small")
    vector = [0.1, 0.2, 0.3, 0.4]
    cache.put(key, vector)
    result = cache.get(key)
    assert result == pytest.approx(vector)
    cache.close()


def test_get_miss_returns_none(tmp_path: Path):
    cache = EmbeddingCache(str(tmp_path / ".embedding_cache.db"))
    result = cache.get("nonexistent_key")
    assert result is None
    cache.close()


def test_key_is_model_sensitive():
    key_a = EmbeddingCache.make_key("hello", "model-a")
    key_b = EmbeddingCache.make_key("hello", "model-b")
    assert key_a != key_b


def test_key_is_text_sensitive():
    key_a = EmbeddingCache.make_key("hello", "model")
    key_b = EmbeddingCache.make_key("world", "model")
    assert key_a != key_b


def test_cache_file_created_in_nested_dir(tmp_path: Path):
    db_path = str(tmp_path / "subdir" / "nested" / ".embedding_cache.db")
    cache = EmbeddingCache(db_path)
    assert Path(db_path).exists()
    cache.close()


def test_put_overwrites_existing_entry(tmp_path: Path):
    cache = EmbeddingCache(str(tmp_path / ".embedding_cache.db"))
    key = EmbeddingCache.make_key("same text", "model")
    cache.put(key, [1.0, 0.0])
    cache.put(key, [0.0, 1.0])
    result = cache.get(key)
    assert result == pytest.approx([0.0, 1.0])
    cache.close()


def test_embedder_cache_avoids_second_api_call(tmp_path: Path):
    """Embedding the same text twice should only call the API once."""
    from webly.embedder.openai_embedder import OpenAIEmbedder

    call_count = 0

    class _FakeResp:
        class _Item:
            embedding = [0.1, 0.2, 0.3, 0.4]
        data = [_Item()]
        class usage:
            prompt_tokens = 5

    class _TrackingEmbedder(OpenAIEmbedder):
        def _call_with_retry(self, fn, **kwargs):
            nonlocal call_count
            call_count += 1
            return _FakeResp()

    embedder = _TrackingEmbedder(
        model_name="text-embedding-3-small",
        api_key="fake-key",
        cache_dir=str(tmp_path),
    )

    v1 = embedder.embed("unique test text for cache test")
    v2 = embedder.embed("unique test text for cache test")

    assert call_count == 1
    assert v1 == v2
