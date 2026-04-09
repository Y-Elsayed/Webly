import sys
import types

from webly.project_config import ProjectConfig
from webly.query_result import QueryResult
from webly.runtime import ProjectRuntime, build_runtime


class _DummyTracker:
    def __init__(self):
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1


class _DummyDb:
    index = object()


class _DummyIngestPipeline:
    def __init__(self):
        self.db = _DummyDb()
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return {"indexed": True}


class _DummyQueryPipeline:
    def query_result(self, question: str, retry_on_empty: bool = False, memory_context: str = ""):
        return QueryResult(
            answer=f"answer:{question}",
            supported=True,
            sources=[],
            trace={"retry_on_empty": retry_on_empty, "memory_context": memory_context},
        )


def test_project_runtime_flushes_tracker_after_query_and_ingest(tmp_path):
    cfg = ProjectConfig.from_dict(
        {"start_url": "https://example.com/docs"},
        output_dir=str(tmp_path / "out"),
        index_dir=str(tmp_path / "out" / "index"),
    )
    tracker = _DummyTracker()
    runtime = ProjectRuntime(
        config=cfg,
        ingest_pipeline=_DummyIngestPipeline(),
        query_pipeline=_DummyQueryPipeline(),
        cost_tracker=tracker,
    )

    result = runtime.query_result("hello", retry_on_empty=True, memory_context="ctx")
    ingest_result = runtime.run_ingest(mode="index_only")

    assert result.answer == "answer:hello"
    assert result.trace["retry_on_empty"] is True
    assert ingest_result == {"indexed": True}
    assert tracker.flush_count == 2


def test_build_runtime_passes_score_threshold_to_query_pipeline(monkeypatch, tmp_path):
    captured = {}

    hf_module = types.ModuleType("webly.embedder.hf_sentence_embedder")

    class DummyEmbedder:
        dim = 4

        def __init__(self, model_name):
            self.model_name = model_name

    hf_module.HFSentenceEmbedder = DummyEmbedder
    monkeypatch.setitem(sys.modules, "webly.embedder.hf_sentence_embedder", hf_module)

    class DummyDb:
        def __init__(self):
            self.index = None

    class DummyCrawler:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.output_dir = kwargs["output_dir"]
            self.results_filename = kwargs["results_filename"]

    class DummyIngest:
        def __init__(self, **kwargs):
            self.db = kwargs["db"]

    class DummyChatModel:
        def __init__(self, api_key: str, model: str, cost_tracker=None):
            self.api_key = api_key
            self.model_name = model
            self.context_window_tokens = 128000

    class DummyAgent:
        def __init__(self, embedder, vector_db, chatbot, system_prompt=None):
            self.embedder = embedder
            self.vector_db = vector_db
            self.chatbot = chatbot
            self.system_prompt = system_prompt
            self.top_k = 5

    class DummyQueryPipelineCtor:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("webly.runtime.Crawler", DummyCrawler)
    monkeypatch.setattr("webly.runtime.FaissDatabase", DummyDb)
    monkeypatch.setattr("webly.runtime.IngestPipeline", DummyIngest)
    monkeypatch.setattr("webly.runtime.ChatGPTModel", DummyChatModel)
    monkeypatch.setattr("webly.runtime.WeblyChatAgent", DummyAgent)
    monkeypatch.setattr("webly.runtime.QueryPipeline", DummyQueryPipelineCtor)

    cfg = ProjectConfig.from_dict(
        {
            "start_url": "https://example.com/docs",
            "allowed_domains": ["example.com"],
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "chat_model": "gpt-4o-mini",
            "score_threshold": 0.72,
        },
        output_dir=str(tmp_path / "out"),
        index_dir=str(tmp_path / "out" / "index"),
    )

    runtime = build_runtime(cfg, api_key="sk-test")

    assert runtime.query_pipeline is not None
    assert captured["score_threshold"] == 0.72
