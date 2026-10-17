from tests.query_eval_harness import ScriptedChatAgent, ScriptedPlanner
from webly.pipeline.query_pipeline import QueryPipeline
from webly.query_result import QueryResult


class _DummyChatbot:
    model_name = "gpt-4o-mini"
    context_window_tokens = 128000

    def generate(self, _prompt: str) -> str:
        return "OK"


class _DummyEmbedder:
    def embed(self, _text: str):
        return [1.0, 0.0]


class _DummyVectorDb:
    def __init__(self, results):
        self._results = list(results)
        self.metadata = []

    def search(self, _query_embedding, top_k=5):
        return list(self._results[:top_k])


class _DummyChatAgent:
    def __init__(self, results):
        self.top_k = 5
        self.chatbot = _DummyChatbot()
        self.embedder = _DummyEmbedder()
        self.vector_db = _DummyVectorDb(results)

    def answer(self, _question: str, _context: str) -> str:
        return "Threshold answer"

    def answer_with_support(self, _question: str, _context: str):
        return "Threshold answer", "Y"

    def rewrite_query(self, _question: str, _hints):
        return None

    def _judge_answerability(self, _question: str, _context: str) -> bool:
        return True


def test_query_result_filters_low_similarity_results_and_keeps_string_api():
    agent = _DummyChatAgent(
        [
            {"id": "hi", "url": "https://docs.example.com/high", "text": "High", "score": 0.91, "hierarchy": ["Docs"]},
            {"id": "lo", "url": "https://docs.example.com/low", "text": "Low", "score": 0.21, "hierarchy": ["Docs"]},
        ]
    )
    qp = QueryPipeline(chat_agent=agent, enable_hybrid=False, score_threshold=0.8)

    result = qp.query_result("threshold question")

    assert isinstance(result, QueryResult)
    assert result.answer == "Threshold answer"
    assert result.supported is True
    assert [source.url for source in result.sources] == ["https://docs.example.com/high"]
    assert qp.query("threshold question") == "Threshold answer"


def test_query_result_falls_back_when_threshold_filters_everything():
    agent = _DummyChatAgent(
        [
            {"id": "lo", "url": "https://docs.example.com/low", "text": "Low", "score": 0.21, "hierarchy": ["Docs"]},
        ]
    )
    qp = QueryPipeline(chat_agent=agent, enable_hybrid=False, score_threshold=0.8)

    result = qp.query_result("threshold question")

    assert result.supported is False
    assert "couldn't find anything" in result.answer.lower()
    assert result.sources == []


def test_classic_rewrite_searches_are_globally_capped():
    agent = ScriptedChatAgent(
        results_by_query={"root": [{"id": "seed", "url": "https://example.test/p", "text": "seed"}]},
        rewrite_fn=lambda _question, _hints: " || ".join(f"followup-{i}" for i in range(10)),
        judge_fn=lambda _question, _context: False,
    )
    searches = []
    original = agent.vector_db.search

    def search(query, top_k=5):
        searches.append(query)
        return original(query, top_k)

    agent.vector_db.search = search
    QueryPipeline(
        chat_agent=agent, retrieval_mode="classic", enable_hybrid=False,
        enable_graph_expansion=False, enable_section_expansion=False,
    ).query_result("root")
    assert searches == ["root", "followup-0", "followup-1", "followup-2"]


def test_builder_followups_are_unique_and_globally_capped():
    planner = ScriptedPlanner(
        followup_payload={"queries": ["next"] * 2 + [f"next-{i}" for i in range(10)], "drop_chunk_ids": []}
    )
    agent = ScriptedChatAgent(
        results_by_query={"root": [{"id": "seed", "url": "https://example.test/p", "text": "seed"}]},
        planner=planner,
        judge_fn=lambda _question, _context: False,
    )
    searches = []
    original = agent.vector_db.search

    def search(query, top_k=5):
        searches.append(query)
        return original(query, top_k)

    agent.vector_db.search = search
    QueryPipeline(chat_agent=agent, retrieval_mode="builder", enable_hybrid=False, builder_max_rounds=4).query_result(
        "root"
    )
    assert searches == ["root", "next", "next-0", "next-1"]
