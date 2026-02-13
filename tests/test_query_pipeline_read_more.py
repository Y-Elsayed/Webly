from pipeline.query_pipeline import QueryPipeline


class _DummyChatbot:
    model_name = "gpt-4o-mini"

    def generate(self, _prompt: str) -> str:
        return "OK"


class _DummyChatAgent:
    def __init__(self):
        self.top_k = 5
        self.chatbot = _DummyChatbot()
        self.embedder = None
        self.vector_db = None

    def answer(self, _question: str, _context: str) -> str:
        return "Base answer"


def test_read_more_uses_only_urls_from_final_assembled_context():
    qp = QueryPipeline(chat_agent=_DummyChatAgent(), allow_best_effort=True)

    # A and B are used to build the final context.
    used_results = [
        {"id": "a#1", "url": "https://docs.example.com/a", "text": "Alpha", "hierarchy": ["Core"]},
        {"id": "b#1", "url": "https://docs.example.com/b", "text": "Beta", "hierarchy": ["Core"]},
    ]
    context = qp._assemble_context(used_results, max_chars=10000)

    # C exists in retrieval universe, but was not used in assembled context.
    all_results = used_results + [{"id": "c#1", "url": "https://docs.example.com/c", "text": "Gamma"}]
    response = qp._best_effort_with_links(
        question_for_answer="Q",
        context=context,
        concepts=["core schema"],
        coverage={"missing": [], "covered": ["core schema"]},
        results=all_results,
    )

    assert "Read more:" in response
    assert "https://docs.example.com/a" in response
    assert "https://docs.example.com/b" in response
    assert "https://docs.example.com/c" not in response


def test_read_more_omitted_when_no_used_sources():
    qp = QueryPipeline(chat_agent=_DummyChatAgent(), allow_best_effort=True)

    qp._last_used_sources = []
    response = qp._best_effort_with_links(
        question_for_answer="Q",
        context="No context",
        concepts=["core schema"],
        coverage={"missing": [], "covered": ["core schema"]},
        results=[{"url": "https://docs.example.com/a", "text": "Alpha"}],
    )

    assert response == "Base answer"
    assert "Read more:" not in response
