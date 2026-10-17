import json
import logging

from webly.chatbot.webly_chat_agent import WeblyChatAgent
from webly.pipeline.query_context import QueryContextTools
from webly.pipeline.query_retriever import QueryRetriever
from webly.processors.text_chunkers import SlidingTextChunker
from webly.vector_index.faiss_db import FaissDatabase


class _Embedder:
    def embed(self, _text):
        return [1, 0]


class _Agent:
    def __init__(self, db):
        self.embedder = _Embedder()
        self.vector_db = db


def test_real_faiss_hybrid_merges_by_segment_and_keeps_both_page_sections(tmp_path):
    db = FaissDatabase()
    db.create(2)
    db.add([
        {"segment_id": "fee", "url": "https://example.test/admissions", "text": "Fee is 10 units",
         "original_text": "Fee is 10 units", "embedding": [1, 0]},
        {"segment_id": "deadline", "url": "https://example.test/admissions", "text": "Deadline is June",
         "original_text": "Deadline is June", "embedding": [0, 1]},
    ])
    db.save(str(tmp_path / "faiss"))
    loaded = FaissDatabase(str(tmp_path / "faiss"))
    retriever = QueryRetriever(_Agent(loaded), logger=logging.getLogger("r0"))
    candidates = retriever.combine_and_rerank(retriever.search("Fee Deadline", k=2, tag="initial"))
    assert {candidate["segment_id"] for candidate in candidates} == {"fee", "deadline"}
    fee = next(candidate for candidate in candidates if candidate["segment_id"] == "fee")
    assert any("semantic" in channel for channel in fee["channel_ranks"])
    assert any("lexical" in channel for channel in fee["channel_ranks"])
    context, sources = QueryContextTools().assemble_context(candidates, max_chars=2000)
    assert "Fee is 10" in context and "Deadline is June" in context
    assert {source["chunk_id"] for source in sources} == {"fee", "deadline"}


def test_arabic_and_english_tokens_survive_normalization():
    retriever = QueryRetriever(None, logger=logging.getLogger("r0"))
    assert "رسوم" in retriever._tokenize("رسوم الدراسة 2026")
    assert "fees" in retriever._tokenize("Fees الرسوم")


def test_nested_html_is_extracted_once_and_large_block_is_split():
    chunker = SlidingTextChunker(max_words=8, overlap=2)
    html = (
        "<h1>Fees</h1><div><section><p>one two three four five six seven eight "
        "nine ten eleven twelve</p></section></div>"
    )
    chunks = chunker.chunk_html(html, "https://example.test/fees")
    assert len(chunks) >= 2
    assert all(chunk["tokens"] <= 8 for chunk in chunks)
    assert all(chunk["hierarchy"] == ["Fees"] for chunk in chunks)
    assert sum(chunk["text"].count("one") for chunk in chunks) == 1


class _JsonChatbot:
    model_name = "gpt-4o-mini"
    context_window_tokens = 8192

    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = 0

    def generate(self, _prompt):
        self.calls += 1
        return next(self.payloads)


def test_grounded_answer_accepts_only_exact_supplied_segment_span():
    chatbot = _JsonChatbot([json.dumps({
        "answer": "The fee is 10 units.", "status": "answered",
        "citations": [{"segment_id": "fee", "supporting_span": "Fee is 10 units"}],
    })])
    agent = WeblyChatAgent(_Embedder(), None, chatbot)
    answer, citations, status, missing = agent.answer_grounded(
        "What is the fee?", "[Evidence: fee] (Source: https://example.test/p)\nFee is 10 units",
        [{"chunk_id": "fee", "url": "https://example.test/p", "original_text": "Fee is 10 units"}],
    )
    assert status == "answered" and missing == [] and answer == "The fee is 10 units."
    assert citations == [{
        "segment_id": "fee", "page_url": "https://example.test/p", "supporting_span": "Fee is 10 units"
    }]


def test_invented_citation_fails_closed_after_one_repair():
    bad = json.dumps({"answer": "A claim", "status": "answered", "citations": [
        {"segment_id": "invented", "supporting_span": "Fee is 10 units"}]})
    chatbot = _JsonChatbot([bad, bad])
    agent = WeblyChatAgent(_Embedder(), None, chatbot)
    answer, citations, status, missing = agent.answer_grounded(
        "fee?", "[Evidence: fee] (Source: https://example.test/p)\nFee is 10 units",
        [{"chunk_id": "fee", "url": "https://example.test/p", "original_text": "Fee is 10 units"}],
    )
    assert status == "unsupported" and missing == [] and citations == [] and "couldn't verify" in answer
    assert chatbot.calls == 2


def test_budget_failure_does_not_call_model():
    chatbot = _JsonChatbot([])
    agent = WeblyChatAgent(_Embedder(), None, chatbot, max_total_tokens=100)
    answer, citations, status, _missing = agent.answer_grounded(
        "question", "[Evidence: fee] (Source: https://example.test/p)\nFee is 10 units",
        [{"chunk_id": "fee", "url": "https://example.test/p", "original_text": "Fee is 10 units"}],
    )
    assert status == "unsupported" and citations == [] and "budget" in answer
    assert chatbot.calls == 0
