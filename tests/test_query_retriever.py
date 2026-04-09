from webly.pipeline.query_retriever import QueryRetriever


class _DummyEmbedder:
    def embed(self, _text: str):
        return [1.0, 0.0]


class _DummyVectorDb:
    def __init__(self, results, metadata=None):
        self._results = list(results)
        self.metadata = list(metadata or [])

    def search(self, _query_embedding, top_k=5):
        return list(self._results[:top_k])


class _DummyChatAgent:
    def __init__(self, results, metadata=None):
        self.embedder = _DummyEmbedder()
        self.vector_db = _DummyVectorDb(results, metadata=metadata)


class _DummyLogger:
    def debug(self, _message: str):
        return None


def test_query_retriever_filters_low_similarity_results():
    retriever = QueryRetriever(
        chat_agent=_DummyChatAgent(
            [
                {"id": "hi", "url": "https://docs.example.com/high", "text": "High", "score": 0.91},
                {"id": "lo", "url": "https://docs.example.com/low", "text": "Low", "score": 0.21},
            ]
        ),
        logger=_DummyLogger(),
        enable_hybrid=False,
        score_threshold=0.8,
    )

    results = retriever.search("threshold question", k=5, tag="initial")

    assert [item["id"] for item in results] == ["hi"]
    assert results[0]["_origin"] == "initial"


def test_query_retriever_combines_and_dedupes_by_canonical_url():
    retriever = QueryRetriever(
        chat_agent=_DummyChatAgent([]),
        logger=_DummyLogger(),
        enable_hybrid=False,
    )

    results = retriever.combine_and_rerank(
        [
            {
                "id": "a",
                "url": "https://docs.example.com/page?utm_source=x",
                "score": 0.8,
                "_score_vec": 0.8,
                "_origin": "initial",
                "_meta_rank": 0,
                "metadata": {"chunk_id": "page-a"},
            },
            {
                "id": "b",
                "url": "https://docs.example.com/page",
                "score": 0.7,
                "_score_vec": 0.7,
                "_origin": "rewrite",
                "_meta_rank": 0,
                "metadata": {"chunk_id": "page-b"},
            },
        ]
    )

    assert len(results) == 1
    assert results[0]["id"] == "a"
