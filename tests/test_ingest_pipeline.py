import os
import sys
import types
from pathlib import Path

# Provide a lightweight stub for processors.text_summarizer to avoid importing tiktoken
_stub_sum = types.ModuleType("processors.text_summarizer")
_stub_sum.TextSummarizer = object
sys.modules.setdefault("processors.text_summarizer", _stub_sum)

_stub_ext = types.ModuleType("processors.text_extractors")
_stub_ext.DefaultTextExtractor = object
sys.modules.setdefault("processors.text_extractors", _stub_ext)

from pipeline.ingest_pipeline import IngestPipeline  # noqa: E402


class DummyCrawler:
    def __init__(self, output_dir: str, results_filename: str = "results.jsonl"):
        self.output_dir = output_dir
        self.results_filename = results_filename

    def crawl(self, *args, **kwargs):
        return None


class DummyEmbedder:
    dim = 4

    def embed(self, text: str):
        return [0.0, 0.0, 0.0, 0.0]


class DummyDB:
    def create(self, dim: int, index_type: str = "flat"):
        return None

    def add(self, records):
        return None

    def save(self, path: str):
        return None


def test_resolve_results_path_prefers_existing(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    results = out_dir / "results.jsonl"
    results.write_text('{"url": "x", "html": "y"}\n', encoding="utf-8")

    crawler = DummyCrawler(str(out_dir))
    pipe = IngestPipeline(
        crawler=crawler,
        index_path=str(tmp_path / "index"),
        embedder=DummyEmbedder(),
        db=DummyDB(),
        summarizer=None,
        debug=False,
    )
    assert pipe._resolve_results_path(require_non_empty=True) == str(results)


def test_run_index_only_with_empty_results(tmp_path: Path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    results = out_dir / "results.jsonl"
    results.write_text("", encoding="utf-8")

    crawler = DummyCrawler(str(out_dir))
    pipe = IngestPipeline(
        crawler=crawler,
        index_path=str(tmp_path / "index"),
        embedder=DummyEmbedder(),
        db=DummyDB(),
        summarizer=None,
        debug=False,
    )
    result = pipe.run(mode="index_only")
    assert result.get("empty_results") is True
    assert os.path.exists(result.get("results_path"))
