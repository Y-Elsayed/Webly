from webly.pipeline.embedding_text import chunk_text_for_embedding


class _SmallEmbedder:
    max_input_tokens = 10
    safety_ratio = 1.0

    def count_tokens(self, text):
        return len(text.encode("utf-8"))


def test_oversized_block_is_split_under_embedding_limit():
    embedder = _SmallEmbedder()
    pieces = chunk_text_for_embedding(embedder, "كلمة" * 30)
    assert len(pieces) > 1
    assert all(embedder.count_tokens(piece) <= 10 for piece in pieces)
