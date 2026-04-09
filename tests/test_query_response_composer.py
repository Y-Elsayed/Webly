from webly.pipeline.query_context import QueryContextTools
from webly.pipeline.query_response_composer import QueryResponseComposer


class _DummyChatAgent:
    def answer_with_support(self, question: str, _context: str):
        if "capital of france" in (question or "").lower():
            return "Base answer", "N"
        return "Base answer", "Y"


def test_query_response_composer_best_effort_uses_only_used_source_links():
    composer = QueryResponseComposer(
        chat_agent=_DummyChatAgent(),
        context_tools=QueryContextTools(),
        max_context_chars=12000,
    )

    answer, supported = composer.best_effort_payload(
        question_for_answer="Q",
        context="Context",
        coverage={"missing": [], "covered": ["core schema"]},
        used_sources=[
            {"chunk_id": "a#1", "url": "https://docs.example.com/a", "section": "Core"},
            {"chunk_id": "b#1", "url": "https://docs.example.com/b", "section": "Core"},
        ],
    )

    assert supported is True
    assert "Read more:" in answer
    assert "https://docs.example.com/a" in answer
    assert "https://docs.example.com/b" in answer


def test_query_response_composer_fallback_returns_no_links_for_off_topic_question():
    composer = QueryResponseComposer(
        chat_agent=_DummyChatAgent(),
        context_tools=QueryContextTools(),
        max_context_chars=12000,
    )

    answer, supported, used_sources = composer.fallback_payload(
        [
            {
                "url": "https://docs.pydantic.dev/dev/concepts/validators/",
                "text": "Pydantic validators define field validation flow.",
                "hierarchy": ["Concepts", "Validators"],
            }
        ],
        "What is the capital of France?",
    )

    assert supported is False
    assert "These pages may help" not in answer
    assert used_sources == [
        {
            "chunk_id": "https://docs.pydantic.dev/dev/concepts/validators/#chunk_-1",
            "url": "https://docs.pydantic.dev/dev/concepts/validators/",
            "section": "Concepts",
        }
    ]
