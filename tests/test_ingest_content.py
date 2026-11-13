import json
from pathlib import Path

import pytest

from tests.test_integration import IntegrationDummyEmbedder, _make_ingest_pipeline
from webly.runtime import ProjectRuntime
from webly.vector_index.faiss_db import FaissDatabase
from webly.vector_index.snapshots import SnapshotStore

HTML = "<h1>Admissions</h1><p>Annual tuition is five thousand dollars.</p>"


def page(url="https://example.test/?page=6", html=HTML):
    return {"url": url, "html": html}


def make_pipe(tmp_path, pages):
    pipe = _make_ingest_pipeline(tmp_path, pages=pages)
    pipe.crawler.crawl()
    return pipe


def report(pipe):
    return json.loads(Path(pipe.ingest_report_path).read_text(encoding="utf-8"))


def test_empty_login_page_skipped_and_reported_while_valid_evidence_publishes(tmp_path):
    pipe = make_pipe(tmp_path, [page(), page("https://example.test/samllogin", "<form><input></form>")])
    progress = []
    pipe.progress_callback = lambda current, total, url: progress.append(current)
    source = Path(pipe.results_path).read_bytes()
    result = pipe.run(mode="index_only")
    assert result["indexed"]
    assert result["ingest_summary"] == {
        "pages_total": 2, "pages_indexed": 1, "pages_skipped": 1,
        "duplicate_pages": 0, "chunks_skipped": 0, "segments_indexed": 1,
    }
    saved = report(pipe)
    assert saved["status"] == "completed"
    assert saved["skipped_pages"] == [{
        "url": "https://example.test/samllogin", "line": 2, "reason": "no_extractable_content",
    }]
    assert saved["index_version"] == SnapshotStore(pipe.index_path).active_version()
    assert progress == [1, 2]
    assert Path(pipe.results_path).read_bytes() == source


def test_identical_cleaned_pages_dedup_before_summary_and_embed_and_keep_aliases(tmp_path):
    first, second = "https://example.test/?page=6", "https://example.test/?page=7"
    pipe = make_pipe(tmp_path, [page(first, HTML + "<script>Ignored script</script>"), page(second, HTML)])
    summaries, embeddings = [], []

    def summarize(url, text):
        summaries.append((url, text))
        return {"summary": "Tuition summary"}

    class CountingEmbedder(IntegrationDummyEmbedder):
        def embed(self, text):
            embeddings.append(text)
            return super().embed(text)

    pipe.summarizer, pipe.use_summary, pipe.embedder = summarize, True, CountingEmbedder()
    pipe.run(mode="index_only")
    store = SnapshotStore(pipe.index_path)
    db = FaissDatabase(str(store.validate(store.active_version())))
    assert len(summaries) == len(embeddings) == db.index.ntotal == 1
    record = db.metadata[0]
    assert record["metadata"]["source_urls"] == [first, second]
    assert record["url"] == first
    assert record["text"] == record["original_text"] == "Annual tuition is five thousand dollars."
    assert record["embedding_text"] == "Tuition summary"
    assert pipe.ingest_summary["duplicate_pages"] == pipe.ingest_summary["chunks_skipped"] == 1
    assert report(pipe)["duplicate_pages"][0]["canonical_url"] == first
    checkpoint = json.loads((Path(pipe.crawler.output_dir) / "checkpoint.json").read_text())
    assert checkpoint["indexed_url_count"] == 1


def test_every_embedding_segment_has_distinct_alias_list_without_repeated_urls(tmp_path):
    first, second = "https://example.test/first", "https://example.test/second"
    pipe = make_pipe(tmp_path, [page(first), page(second), page(second)])
    pipe._chunk_for_embedding = lambda text: [text[:20], text[20:]]
    records = pipe.transform()
    assert len(records) == 2
    assert all(r["metadata"]["source_urls"] == [first, second] for r in records)
    assert records[0]["metadata"]["source_urls"] is not records[1]["metadata"]["source_urls"]
    assert all(r["metadata"]["seg_count"] == 2 for r in records)
    assert pipe.ingest_summary["duplicate_pages"] == 2


@pytest.mark.parametrize("other", [
    "<h1>Admissions</h1><p>Annual tuition is six thousand dollars.</p>",
    "<h1>Different heading</h1><p>Annual tuition is five thousand dollars.</p>",
    HTML + "<h2>Deadline</h2><p>Applications must arrive before June first.</p>",
    HTML + "<footer>Contact the visitor desk at 12345.</footer>",
])
def test_genuine_pagination_and_partial_overlap_keep_unique_evidence(tmp_path, other):
    pipe = make_pipe(tmp_path, [page(), page("https://example.test/?page=7", other)])
    pipe.transform()
    assert pipe.ingest_summary["pages_indexed"] == 2
    assert pipe.ingest_summary["duplicate_pages"] == 0


def test_fingerprint_normalizes_whitespace_but_preserves_order_boundaries_and_text(tmp_path):
    pipe = make_pipe(tmp_path, [page(), page("https://example.test/other", HTML.replace(" ", "  "))])
    records = pipe.transform()
    assert pipe.ingest_summary["duplicate_pages"] == 1
    assert records[0]["original_text"] == "Annual tuition is five thousand dollars."
    chunks = [{"hierarchy": ["A"], "text": "one two"}, {"hierarchy": ["B"], "text": "three four"}]
    assert pipe._content_fingerprint(chunks) != pipe._content_fingerprint(list(reversed(chunks)))
    assert pipe._content_fingerprint(chunks) != pipe._content_fingerprint([
        {"hierarchy": ["A"], "text": "one"}, {"hierarchy": ["B"], "text": "two three four"},
    ])


def test_dedup_state_reset_and_canonical_ids_unchanged(tmp_path):
    pipe = make_pipe(tmp_path, [page()])
    alone = pipe.transform()[0]
    pipe.crawler._pages.append(page("https://example.test/alias"))
    pipe.crawler.crawl()
    combined = pipe.transform()[0]
    assert combined["id"] == alone["id"]
    assert pipe.ingest_summary["pages_indexed"] == 1
    assert pipe.ingest_summary["duplicate_pages"] == 1
    pipe.transform()
    assert pipe.ingest_summary["pages_total"] == 2
    assert pipe.ingest_summary["pages_indexed"] == 1


@pytest.mark.parametrize("invalid", [{"url": "https://example.test/bad"}, [], {"url": [], "html": "<p>Text</p>"}])
def test_bad_records_still_abort_with_record_location_and_failed_report(tmp_path, invalid):
    pipe = make_pipe(tmp_path, [page(), invalid])
    with pytest.raises(RuntimeError, match="transform crawl record on line 2"):
        pipe.run(mode="index_only")
    assert report(pipe)["status"] == "failed"
    assert SnapshotStore(pipe.index_path).active_version() is None


def test_malformed_json_still_fails(tmp_path):
    pipe = make_pipe(tmp_path, [page()])
    with Path(pipe.results_path).open("a") as stream:
        stream.write("invalid json\n")
    with pytest.raises(RuntimeError, match="Invalid crawl record on line 2: malformed JSON"):
        pipe.run(mode="index_only")
    assert report(pipe)["status"] == "failed"


def test_all_empty_preserves_previous_active_snapshot(tmp_path):
    pipe = make_pipe(tmp_path, [page()])
    pipe.run(mode="index_only")
    store = SnapshotStore(pipe.index_path)
    old = store.active_version()
    pipe.crawler._pages = [page(html="<form><input></form>")]
    pipe.crawler.crawl()
    with pytest.raises(RuntimeError, match="No usable evidence remains"):
        pipe.run(mode="index_only")
    assert store.active_version() == old
    assert FaissDatabase(str(store.validate(old))).index.ntotal == 1
    assert report(pipe)["summary"]["pages_skipped"] == 1
    assert report(pipe)["status"] == "failed"


def test_embedding_failure_redacts_key_and_preserves_snapshot_and_closes_debug_files(tmp_path, monkeypatch):
    pipe = make_pipe(tmp_path, [page()])
    pipe.run(mode="index_only")
    old = SnapshotStore(pipe.index_path).active_version()
    pipe.debug = True
    opened = []
    original_open = open

    def tracking_open(*args, **kwargs):
        stream = original_open(*args, **kwargs)
        if str(args[0]) in {pipe.debug_chunks_path, pipe.debug_summary_path}:
            opened.append(stream)
        return stream

    class FailingEmbedder(IntegrationDummyEmbedder):
        api_key = "sk-private-key-value"

        def embed(self, text):
            raise RuntimeError(f"Provider rejected {self.api_key}")

    pipe.embedder = FailingEmbedder()
    monkeypatch.setattr("builtins.open", tracking_open)
    with pytest.raises(RuntimeError, match="https://example.test/.*Provider rejected") as failure:
        pipe.run(mode="index_only")
    assert "sk-private-key-value" not in str(failure.value)
    assert "sk-private-key-value" not in Path(pipe.ingest_report_path).read_text()
    assert all(stream.closed for stream in opened) and len(opened) == 2
    assert SnapshotStore(pipe.index_path).active_version() == old


def test_extraction_exception_is_fatal_instead_of_silently_skipped(tmp_path, monkeypatch):
    pipe = make_pipe(tmp_path, [page()])

    def broken(*args):
        raise ValueError("Extraction malfunction")

    monkeypatch.setattr(pipe.page_processor, "process", broken)
    with pytest.raises(RuntimeError, match="line 1.*Extraction malfunction"):
        pipe.run(mode="index_only")
    assert report(pipe)["status"] == "failed"
    assert pipe.ingest_summary["pages_skipped"] == 0


def test_publication_failure_report_is_failed_and_preserves_active(tmp_path, monkeypatch):
    pipe = make_pipe(tmp_path, [page()])
    pipe.run(mode="index_only")
    old = SnapshotStore(pipe.index_path).active_version()

    def fail(*args, **kwargs):
        raise OSError("Publication failure")

    monkeypatch.setattr(SnapshotStore, "publish", fail)
    with pytest.raises(RuntimeError, match="Publication failure"):
        pipe.run(mode="index_only")
    assert report(pipe)["status"] == "failed"
    assert SnapshotStore(pipe.index_path).active_version() == old


def test_failed_runtime_build_forces_reload_of_previous_snapshot(tmp_path):
    from types import SimpleNamespace

    pipe = make_pipe(tmp_path, [page()])
    pipe.run(mode="index_only")
    tracker = SimpleNamespace(flush=lambda: None)
    runtime = ProjectRuntime(
        config=SimpleNamespace(index_dir=pipe.index_path), ingest_pipeline=pipe,
        query_pipeline=None, cost_tracker=tracker,
    )
    assert runtime.ensure_index_loaded()
    old = runtime._loaded_version
    pipe.crawler._pages = [page(html="<form><input></form>")]
    pipe.crawler.crawl()
    with pytest.raises(RuntimeError, match="No usable evidence"):
        runtime.run_ingest(mode="index_only")
    assert runtime._loaded_version is None
    assert runtime.ensure_index_loaded()
    assert runtime._loaded_version == old
    assert runtime.db.index.ntotal == 1


@pytest.mark.parametrize("invalid_input", [False, True])
def test_report_publication_and_cleanup_failures_do_not_change_ingest_outcome(tmp_path, monkeypatch, invalid_input):
    import os

    pipe = make_pipe(tmp_path, [{}] if invalid_input else [page()])
    replace, unlink = os.replace, os.unlink

    def deny_report_replace(source, destination):
        if Path(destination).name == "ingest_report.json":
            raise PermissionError("Report destination locked")
        return replace(source, destination)

    def deny_report_cleanup(path, *args, **kwargs):
        if Path(path).name.startswith(".ingest-report-"):
            raise PermissionError("Report cleanup denied")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "replace", deny_report_replace)
    monkeypatch.setattr(os, "unlink", deny_report_cleanup)
    if invalid_input:
        with pytest.raises(RuntimeError, match="Failed to transform crawl record on line 1"):
            pipe.run(mode="index_only")
        assert SnapshotStore(pipe.index_path).active_version() is None
    else:
        result = pipe.run(mode="index_only")
        assert result["indexed"]
        assert result["ingest_report_path"] is None
        store = SnapshotStore(pipe.index_path)
        assert FaissDatabase(str(store.validate(store.active_version()))).index.ntotal == 1
    assert not pipe._report_written
