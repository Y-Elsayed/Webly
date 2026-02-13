from pipeline.query_pipeline import QueryPipeline


class _DummyChatbot:
    def __init__(self, model_name: str, context_window_tokens: int):
        self.model_name = model_name
        self.context_window_tokens = context_window_tokens


class _DummyChatAgent:
    def __init__(self, chatbot):
        self.top_k = 5
        self.chatbot = chatbot
        self.embedder = None
        self.vector_db = None


def test_budget_scales_with_large_model_context_window():
    agent = _DummyChatAgent(_DummyChatbot("gpt-4o-mini", 128000))
    qp = QueryPipeline(chat_agent=agent, max_context_chars=12000)
    budget = qp._compute_budget_chars("question")
    assert budget > 12000


def test_budget_respects_small_context_window():
    agent = _DummyChatAgent(_DummyChatbot("gpt-3.5-turbo", 16000))
    qp = QueryPipeline(chat_agent=agent, max_context_chars=12000)
    budget = qp._compute_budget_chars("question")
    assert budget == 54400
