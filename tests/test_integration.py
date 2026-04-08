"""
End-to-end integration tests for the Webly pipeline.

Uses real FAISS and real chunking/extraction, but stubs out network and LLM calls.
Follows the existing test patterns (dummy objects, tmp_path, no mocking library).
"""

import json
import sys
import types
from pathlib import Path

import pytest

# ── Stub heavy optional imports (same pattern as test_ingest_pipeline.py) ────

_stub_sum = types.ModuleType("webly.processors.text_summarizer")
_stub_sum.TextSummarizer = object
sys.modules.setdefault("webly.processors.text_summarizer", _stub_sum)

FaissDatabase = pytest.importorskip("webly.vector_index.faiss_db", exc_type=ImportError).FaissDatabase

from webly.pipeline.ingest_pipeline import IngestPipeline  # noqa: E402

# ── Dummy classes ─────────────────────────────────────────────────────────────


class IntegrationDummyCrawler:
    """Writes synthetic pages to results.jsonl without hitting the network."""

    def __init__(self, output_dir: str, pages: list[dict]):
        self.output_dir = output_dir
        self.results_filename = "results.jsonl"
        self._pages = pages
        self.crawl_called = False

    def crawl(self, *args, **kwargs):
        self.crawl_called = True
        path = Path(self.output_dir) / self.results_filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for p in self._pages:
                f.write(json.dumps(p) + "\n")


class IntegrationDummyEmbedder:
    """Returns deterministic dim-4 vectors so no OpenAI key is required."""

    dim = 4
    max_input_tokens = 8192

    def embed(self, text: str) -> list[float]:
        import hashlib
        h = int(hashlib.md5(text.encode(), usedforsecurity=False).hexdigest(), 16)
        return [(h >> (i * 8) & 0xFF) / 255.0 for i in range(self.dim)]

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


_SYNTHETIC_PAGES = [
    {
        "url": "https://example.com/page1",
        "html": "<html><body><h1>France</h1><p>The capital of France is Paris.</p></body></html>",
        "crawled_at": "2026-04-07T12:00:00+00:00",
    }
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_ingest_pipeline(tmp_path: Path, pages=None) -> IngestPipeline:
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    idx_dir = tmp_path / "idx"
    crawler = IntegrationDummyCrawler(str(out_dir), _SYNTHETIC_PAGES if pages is None else pages)
    db = FaissDatabase()
    return IngestPipeline(
        crawler=crawler,
        index_path=str(idx_dir),
        embedder=IntegrationDummyEmbedder(),
        db=db,
        summarizer=None,
        use_summary=False,
        debug=False,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_full_ingest_cycle(tmp_path: Path):
    """crawl → transform → load should produce a valid on-disk FAISS index."""
    pipe = _make_ingest_pipeline(tmp_path)
    result = pipe.run(mode="both")

    assert result["indexed"] is True
    assert (Path(tmp_path) / "idx" / "embeddings.index").exists()
    assert (Path(tmp_path) / "idx" / "metadata.json").exists()

    # Checkpoint written with correct stage
    checkpoint = json.loads((Path(tmp_path) / "out" / "checkpoint.json").read_text())
    assert checkpoint["stage"] == "load_done"

    # Reload index and search
    db2 = FaissDatabase(str(tmp_path / "idx"))
    query_vec = IntegrationDummyEmbedder().embed("capital France")
    results = db2.search(query_vec, top_k=3)
    assert len(results) > 0


def test_crawled_at_preserved_in_index(tmp_path: Path):
    """crawled_at from results.jsonl should appear in FAISS metadata."""
    pipe = _make_ingest_pipeline(tmp_path)
    pipe.run(mode="both")

    db2 = FaissDatabase(str(tmp_path / "idx"))
    query_vec = IntegrationDummyEmbedder().embed("capital France")
    results = db2.search(query_vec, top_k=3)
    assert any(
        r.get("metadata", {}).get("crawled_at") == "2026-04-07T12:00:00+00:00"
        for r in results
    )


def test_resume_skips_crawl_when_results_exist(tmp_path: Path):
    """If results.jsonl already exists, a non-forced run must not re-crawl."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Pre-populate results
    (out_dir / "results.jsonl").write_text(
        json.dumps(_SYNTHETIC_PAGES[0]) + "\n", encoding="utf-8"
    )

    crawler = IntegrationDummyCrawler(str(out_dir), _SYNTHETIC_PAGES)
    db = FaissDatabase()
    pipe = IngestPipeline(
        crawler=crawler,
        index_path=str(tmp_path / "idx"),
        embedder=IntegrationDummyEmbedder(),
        db=db,
        summarizer=None,
        use_summary=False,
    )
    pipe.run(mode="both", force_crawl=False)
    assert not crawler.crawl_called


def test_empty_crawl_returns_graceful_result(tmp_path: Path):
    """A crawler that produces no pages should return empty_results=True without raising."""
    pipe = _make_ingest_pipeline(tmp_path, pages=[])
    result = pipe.run(mode="both")
    assert result.get("empty_results") is True
    assert result.get("indexed") is False


def test_index_version_roundtrip(tmp_path: Path):
    """After ingest, corrupting the index version should raise RuntimeError on reload."""
    pipe = _make_ingest_pipeline(tmp_path)
    pipe.run(mode="both")

    meta_path = tmp_path / "idx" / "metadata.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data["config"]["index_version"] = 99
    meta_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(RuntimeError, match="version mismatch"):
        FaissDatabase(str(tmp_path / "idx"))


def test_html_saver_includes_crawled_at():
    """HTMLSaver must add a crawled_at ISO timestamp to every page dict."""
    from datetime import datetime, timezone

    from webly.crawl.handlers import HTMLSaver

    saver = HTMLSaver()
    result = saver("https://example.com", "<html><body>hello</body></html>")
    assert "crawled_at" in result
    # Should be parseable as an ISO 8601 datetime
    parsed = datetime.fromisoformat(result["crawled_at"])
    assert parsed.tzinfo is not None
