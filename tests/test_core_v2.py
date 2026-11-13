"""Core contracts exercised with actual storage and deterministic providers."""

import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import httpcore
import pytest

from webcreeper.creeper_core.safe_fetch import Decoder, FetchError, FetchPolicy, SafeFetcher, ValidatingBackend
from webly import ModelCapabilities, OperationContext, OperationLimits, ProviderBundle, ResourceScope, build_runtime
from webly.contracts import (
    ArtifactError,
    BudgetExceeded,
    ConfigurationError,
    OperationCancelled,
    PolicyError,
    PublicationConflict,
    PublicationUncertain,
    UsageDeliveryError,
    operation_scope,
)
from webly.embedder.embedding_cache import EmbeddingCache
from webly.observability.cost_tracker import CostTracker
from webly.providers import AccountedProvider
from webly.vector_index.snapshots import SnapshotStore

FACT = "The observatory opens every Tuesday morning at nine."


class Embeddings:
    dim = 4

    def __init__(self):
        self.calls = 0
        self.closed = 0
        self.api_key = "fixture-secret-marker"

    def count_tokens(self, text):
        return len(text.split())

    def embed(self, text):
        self.calls += 1
        return [1.0, float("Tuesday" in text), 0.0, 0.0]

    def close(self):
        self.closed += 1


class Chat:
    def __init__(self, fact=FACT):
        self.fact = fact
        self.calls = 0

    def count_tokens(self, text):
        return len(text.split())

    def generate(self, prompt):
        import re

        self.calls += 1
        if "Sufficient?" in prompt:
            return "YES"
        if "Task: route" in prompt:
            return json.dumps({"mode": "retrieve_new", "concepts": [], "requirements": ["Opening times"]})
        if "Task: assess" in prompt:
            return json.dumps({"coverage": [], "queries": []})
        if "Cite only Evidence IDs" in prompt:
            blocks = re.findall(r"\[Evidence: ([^\]]+)\](.*?)(?=\[Evidence: |\Z)", prompt, re.DOTALL)
            sid = next(sid for sid, text in blocks if self.fact in text)
            return json.dumps(
                {
                    "answer": self.fact,
                    "status": "answered",
                    "missing_information": [],
                    "citations": [{"segment_id": sid, "supporting_span": self.fact}],
                }
            )
        return "SAME"


def bundle(fact=FACT, revision="1"):
    return ProviderBundle(
        Embeddings(),
        ModelCapabilities("fixture-embedding", 8192, dimensions=4, revision=revision),
        Chat(fact),
        ModelCapabilities("fixture-chat", 128000),
    )


def make_runtime(root, *, fact=FACT, revision="1", mode="classic"):
    providers = bundle(fact, revision)
    runtime = build_runtime(
        {"start_url": "https://example.test/", "retrieval_mode": mode},
        resources=ResourceScope("fixture", root),
        providers=providers,
    )
    return runtime


def import_pages(runtime, tmp_path, pages):
    path = tmp_path / "import.jsonl"
    path.write_text("".join(json.dumps({"url": url, "html": html}) + "\n" for url, html in pages), encoding="utf-8")
    return runtime.import_legacy(path, acknowledge_complete=True)


def page(url="https://example.test/", fact=FACT):
    return url, f"<h1>Opening hours</h1><p>{fact}</p>"


def test_explicit_runtime_resources_secrets_lifecycle_and_unknown_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-secret-marker")
    with pytest.raises(TypeError):
        build_runtime({"start_url": "https://example.test"})
    runtime = make_runtime(tmp_path / "core")
    assert "fixture-secret-marker" not in repr(runtime)
    assert "fixture-secret-marker" not in repr(runtime.providers)
    runtime.close()
    runtime.close()
    assert runtime.providers.embedder.closed == 0  # injected clients are caller owned
    runtime.providers.close()
    runtime.providers.close()
    assert runtime.providers.embedder.closed == 1
    with pytest.raises(ConfigurationError):
        runtime.query_result("question")
    with pytest.raises(ValueError, match="Unknown"):
        build_runtime(
            {"start_url": "https://example.test/", "typo": True},
            resources=ResourceScope("other", tmp_path / "other"),
            providers=bundle(),
        )


def test_resource_ownership_and_path_containment(tmp_path):
    scope = ResourceScope("a", tmp_path / "a")
    with pytest.raises(PublicationConflict):
        ResourceScope("b", tmp_path / "a")
    for name in ("..", "../outside", "/absolute", "C:\\secret", "a/b", ".hidden"):
        with pytest.raises(PolicyError):
            scope.path(name)


def test_import_build_query_replay_and_conflicting_operation_id(tmp_path):
    runtime = make_runtime(tmp_path / "core")
    run = import_pages(runtime, tmp_path, [page()])
    context = OperationContext(operation_id="build-1", limits=OperationLimits.ingest())
    result = runtime.run_ingest(mode="index_only", run_id=run, context=context)
    assert result.outcome.state == "committed"
    assert runtime.inspect_run(run)["status"] == "completed"
    calls = runtime.providers.embedder.calls
    replay = runtime.run_ingest(
        mode="index_only", run_id=run, context=OperationContext(operation_id="build-1", limits=OperationLimits.ingest())
    )
    assert replay["indexed"] and runtime.providers.embedder.calls == calls
    with pytest.raises(PublicationConflict):
        runtime.run_ingest(mode="crawl_only", context=OperationContext(operation_id="build-1"))
    answer = runtime.query_result("When does the observatory open?")
    assert answer.answer == FACT and answer.citations
    assert "query" not in answer.trace and "assessments" not in answer.trace
    runtime.close()


def test_removal_requires_exact_approval_and_stale_approval_fails(tmp_path):
    runtime = make_runtime(tmp_path / "core")
    first = import_pages(
        runtime, tmp_path, [page(), page("https://example.test/other", "Visitors reserve tickets online.")]
    )
    runtime.run_ingest(mode="index_only", run_id=first)
    old = SnapshotStore(runtime.config.index_dir).active_version()
    second = import_pages(runtime, tmp_path, [page()])
    pending = runtime.run_ingest(mode="index_only", run_id=second)
    assert pending["status"] == "approval_required"
    assert pending["proposal"]["removed"] == ["https://example.test/other"]
    assert SnapshotStore(runtime.config.index_dir).active_version() == old
    approved = runtime.run_ingest(mode="index_only", run_id=second, approval=pending["proposal"]["approval_token"])
    assert approved["indexed"] and approved.outcome.state == "committed"
    # The old approval cannot approve removal from a different active corpus.
    runtime.run_ingest(mode="index_only", run_id=first)
    stale = runtime.run_ingest(mode="index_only", run_id=second, approval=pending["proposal"]["approval_token"])
    assert stale["status"] == "approval_required"
    runtime.close()


def test_frozen_run_and_incomplete_run_rejected(tmp_path):
    runtime = make_runtime(tmp_path / "core")
    run = import_pages(runtime, tmp_path, [page()])
    root = runtime.resources.path("runs", run)
    (root / ".crawl_incomplete").write_text("interrupted")
    with pytest.raises(ArtifactError):
        runtime.run_ingest(mode="index_only", run_id=run)
    (root / ".crawl_incomplete").unlink()
    with (root / "results.jsonl").open("a") as stream:
        stream.write("{}\n")
    with pytest.raises(ArtifactError):
        runtime.run_ingest(mode="index_only", run_id=run)
    with pytest.raises(ConfigurationError):
        runtime.import_legacy(root / "results.jsonl")
    runtime.close()


def test_post_commit_fault_is_typed_and_reconciles_without_reembedding(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path / "core")
    run = import_pages(runtime, tmp_path, [page()])
    original = SnapshotStore._sync_directory

    def fail_after_pointer(path):
        if Path(path) == Path(runtime.config.index_dir):
            raise OSError("Injected post-commit fault")
        original(path)

    monkeypatch.setattr(SnapshotStore, "_sync_directory", staticmethod(fail_after_pointer))
    with pytest.raises(PublicationUncertain) as failure:
        runtime.run_ingest(
            mode="index_only",
            run_id=run,
            context=OperationContext(operation_id="uncertain", limits=OperationLimits.ingest()),
        )
    assert failure.value.outcome.state == "uncertain" and failure.value.outcome.snapshot_id
    calls = runtime.providers.embedder.calls
    recovered = runtime.run_ingest(
        mode="index_only",
        run_id=run,
        context=OperationContext(operation_id="uncertain", limits=OperationLimits.ingest()),
    )
    assert recovered["recovered"] and runtime.providers.embedder.calls == calls
    runtime.close()


def test_export_restore_and_model_mismatch(tmp_path):
    runtime = make_runtime(tmp_path / "core")
    run = import_pages(runtime, tmp_path, [page()])
    runtime.run_ingest(mode="index_only", run_id=run)
    runtime.export_snapshot(tmp_path / "backup")
    restored = make_runtime(tmp_path / "restore")
    restored.restore_snapshot(tmp_path / "backup")
    assert restored.query_result("When does the observatory open?").answer == FACT
    with pytest.raises(ConfigurationError):
        restored.restore_snapshot(tmp_path / "backup")
    changed = make_runtime(tmp_path / "changed", revision="different")
    with pytest.raises(RuntimeError, match="Embedding space"):
        changed.restore_snapshot(tmp_path / "backup")
    for item in (runtime, restored, changed):
        item.close()


def test_scopes_do_not_mix_vectors_or_evidence_under_concurrency(tmp_path):
    fact = "تبدأ المحاضرات يوم الأحد الساعة التاسعة صباحا."
    left, right = make_runtime(tmp_path / "left"), make_runtime(tmp_path / "right", fact=fact)
    first = import_pages(left, tmp_path, [page()])
    second = import_pages(right, tmp_path, [page(fact=fact)])
    for runtime, run in ((left, first), (right, second)):
        runtime.run_ingest(mode="index_only", run_id=run)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda runtime: runtime.query_result("When?").answer, [left, right] * 4))
    assert results == [FACT, fact] * 4
    left.close()
    right.close()


def test_budget_cancellation_and_failed_usage_sink_keep_outcomes(tmp_path):
    provider = bundle()
    client = AccountedProvider(provider.embedder, provider.embedding, "embedding")
    context = OperationContext(limits=OperationLimits(provider_attempts=1))
    with operation_scope(context):
        client.embed("first")
        with pytest.raises(BudgetExceeded):
            client.embed("second")
    context = OperationContext()
    context.cancelled.set()
    with pytest.raises(OperationCancelled), operation_scope(context):
        client.embed("not called")

    def broken_sink(event):
        if event["kind"] == "usage":
            raise OSError("Offline sink")

    context = OperationContext(sink=broken_sink)
    with operation_scope(context):
        client.embed("first")
        with pytest.raises(UsageDeliveryError):
            client.embed("second")
    assert context.pending_events and context.summary()["provider_attempts"] == 1


def test_failed_legacy_usage_flush_retains_events(tmp_path):
    tracker = CostTracker(str(tmp_path))
    tracker.record_embedding("fixture", 10)
    (tmp_path / "usage_log.jsonl").mkdir()
    with pytest.raises(OSError):
        tracker.flush()
    assert tracker.totals()["total_tokens"] == 10


def test_cache_namespaces_dimensions_and_concurrent_access(tmp_path):
    cache = EmbeddingCache(str(tmp_path / "cache.sqlite"))
    assert cache.make_key("a", "model", dimensions=2) != cache.make_key("a", "model", dimensions=4)
    assert cache.make_key("a", "model", namespace="left") != cache.make_key("a", "model", namespace="right")

    def write(i):
        key = cache.make_key(str(i), "fixture")
        cache.put(key, [float(i)])
        return cache.get(key)

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(write, range(30))) == [[float(i)] for i in range(30)]
    cache.close()
    cache.close()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[64:ff9b::7f00:1]/",
        "http://10.0.0.1/",
        "http://user:pass@example.com/",
        "file:///etc/passwd",
        "http://example.com:8080/",
        "http://224.0.0.1/",
    ],
)
def test_safe_fetch_rejects_unsafe_destinations_without_network(url):
    with pytest.raises(FetchError):
        FetchPolicy().validate_url(url)


def test_dns_pin_rejects_mixed_answers_before_connecting():
    resolver = SimpleNamespace(resolve=lambda *args, **kwargs: ["1.1.1.1", "127.0.0.1"])
    connected = []
    backend = SimpleNamespace(connect_tcp=lambda *args, **kwargs: connected.append(args))
    checked = ValidatingBackend(FetchPolicy(), OperationContext(), resolver=resolver, backend=backend)
    with pytest.raises(FetchError, match="unsafe_address"):
        checked.connect_tcp("example.test", 80)
    assert not connected
    resolver.resolve = lambda *args, **kwargs: ["1.1.1.1"]
    checked.connect_tcp("example.test", 80)
    assert connected[0][0] == "1.1.1.1"  # backend cannot re-resolve the origin


def test_streamed_compression_and_total_byte_limits():
    context = OperationContext(limits=OperationLimits(response_bytes=128, total_bytes=1024))
    decoder = Decoder({"content-encoding": "gzip", "content-type": "text/html"}, context)
    with pytest.raises(FetchError):
        decoder.feed(gzip.compress(b"x" * 10000))
    context = OperationContext(limits=OperationLimits(response_bytes=100, total_bytes=5))
    decoder = Decoder({}, context)
    with pytest.raises(BudgetExceeded):
        decoder.feed(b"123456")


def test_redirect_to_private_network_rejected_before_second_connection():
    context = OperationContext()
    fetcher = SafeFetcher(context=context)
    response = b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/\r\nContent-Length: 0\r\n\r\n"
    fetcher.sync_pool.close()
    fetcher.sync_pool = httpcore.ConnectionPool(network_backend=httpcore.MockBackend([response]))
    with pytest.raises(FetchError):
        fetcher.fetch("http://1.1.1.1/")
    fetcher.close()


def test_short_facts_bare_container_text_tables_and_code_survive():
    from webly.processors.text_chunkers import SlidingTextChunker

    html = (
        "<h1>Admissions</h1><div>Fee: 100</div><p>Deadline: June 1</p>"
        "<p>Longer introductory text without factual details.</p>"
        "<table><tr><th>Course</th><th>Fee</th></tr><tr><td>Physics</td><td>900</td></tr></table>"
        "<pre>def test():\n    return 42</pre>"
    )
    chunks = SlidingTextChunker(max_words=30).chunk_html(html, "https://example.test/")
    text = "\n".join(chunk["text"] for chunk in chunks)
    assert all(fact in text for fact in ("Fee: 100", "Deadline: June 1", "Physics", "900", "return 42"))
    assert "\n    return 42" in text
    assert all(block["offset_basis"] == "section_extracted_text" for ch in chunks for block in ch["blocks"])


def test_wrong_visible_id_citation_fails_after_bounded_repair():
    from webly.chatbot.webly_chat_agent import WeblyChatAgent

    class WrongId(Chat):
        def generate(self, prompt):
            self.calls += 1
            return json.dumps(
                {
                    "answer": "The fee is 100",
                    "status": "answered",
                    "missing_information": [],
                    "citations": [{"segment_id": "a", "supporting_span": "Fee: 100"}],
                }
            )

    model = WrongId()
    answer = WeblyChatAgent(None, None, model).answer_grounded(
        "What is the fee?",
        (
            "[Evidence: a] (Source: https://example.test/a)\nIntroduction only.\n\n---\n\n"
            "[Evidence: b] (Source: https://example.test/b)\nFee: 100"
        ),
        [
            {"chunk_id": "a", "url": "https://example.test/a", "original_text": "Introduction only. Fee: 100"},
            {"chunk_id": "b", "url": "https://example.test/b", "original_text": "Fee: 100"},
        ],
    )
    assert answer[2] == "unsupported" and model.calls == 2


def test_query_result_limit_is_honored():
    from webly.chatbot.webly_chat_agent import WeblyChatAgent
    from webly.pipeline.query_pipeline import QueryPipeline

    assert QueryPipeline(WeblyChatAgent(None, None, Chat()), max_results_to_consider=3).max_results_to_consider == 3


def test_duplicate_visible_pages_still_discover_distinct_links(tmp_path):
    from webly._webcreeper import Atlas

    base = "https://example.test"
    pages = {
        base + "/": '<p>Directory</p><a href="/a">First</a><a href="/b">Second</a>',
        base + "/a": '<p>Identical visible content.</p><a href="/leaf-a">Details</a>',
        base + "/b": '<p>Identical visible content.</p><a href="/leaf-b">Details</a>',
        base + "/leaf-a": "<p>One</p>",
        base + "/leaf-b": "<p>Two</p>",
    }
    crawler = Atlas({"base_url": base, "storage_path": str(tmp_path), "respect_robots": False})

    async def fetch(url):
        return pages[url], "text/html"

    crawler.fetch_async = fetch
    crawler.crawl(base + "/")
    assert set(crawler.graph) == set(pages)


def test_transient_retries_share_attempt_budget_and_quota_errors_fail_promptly():
    class Transient(Embeddings):
        def embed(self, text):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("Transient timeout")
            return [1, 0, 0, 0]

    raw = Transient()
    client = AccountedProvider(raw, ModelCapabilities("fixture", 8192, dimensions=4), "embedding")
    context = OperationContext()
    with operation_scope(context):
        assert client.embed("hello") == [1, 0, 0, 0]
    assert context.summary()["provider_attempts"] == 2

    class QuotaError(Exception):
        status_code = 429

    class Quota(Embeddings):
        def embed(self, text):
            self.calls += 1
            raise QuotaError("insufficient_quota fixture-secret-marker")

    raw = Quota()
    client = AccountedProvider(raw, ModelCapabilities("fixture", 8192, dimensions=4), "embedding")
    with operation_scope(OperationContext()), pytest.raises(Exception) as error:
        client.embed("hello")
    assert raw.calls == 1 and "fixture-secret-marker" not in str(error.value)


def test_async_fetch_is_bounded_per_host_without_network():
    import asyncio
    from contextlib import asynccontextmanager

    class Pool:
        active = 0
        peak = 0

        @asynccontextmanager
        async def stream(self, *args, **kwargs):
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.01)
                yield SimpleNamespace(status=200, headers=[(b"Content-Type", b"text/html")], aiter_stream=self.body)
            finally:
                self.active -= 1

        async def body(self):
            yield b"ok"

        async def aclose(self):
            pass

    async def run():
        fetcher = SafeFetcher(context=OperationContext(limits=OperationLimits(host_interval_s=0)))
        pool = Pool()
        fetcher.async_pool = pool
        results = await asyncio.gather(*(fetcher.fetch_async(f"https://1.1.1.1/{i}") for i in range(8)))
        assert results == [("ok", "text/html")] * 8
        assert pool.peak <= 2
        await fetcher.aclose()

    asyncio.run(run())


def _crash_after_publication(root, run_id):
    import os

    runtime = make_runtime(Path(root))
    original = SnapshotStore._write_pointer

    def crash(self, version):
        original(self, version)
        os._exit(91)

    SnapshotStore._write_pointer = crash
    runtime.run_ingest(
        mode="index_only",
        run_id=run_id,
        context=OperationContext(operation_id="killed-worker", limits=OperationLimits.ingest()),
    )


def test_process_death_after_commit_recovers_from_operation_identity(tmp_path):
    import multiprocessing

    root = tmp_path / "core"
    runtime = make_runtime(root)
    run = import_pages(runtime, tmp_path, [page()])
    worker = multiprocessing.get_context("spawn").Process(target=_crash_after_publication, args=(str(root), run))
    worker.start()
    worker.join(timeout=20)
    try:
        assert worker.exitcode == 91
        result = runtime.run_ingest(
            mode="index_only",
            run_id=run,
            context=OperationContext(operation_id="killed-worker", limits=OperationLimits.ingest()),
        )
        assert result["recovered"] and result.outcome.state == "committed"
        assert runtime.providers.embedder.calls == 0
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join()
        runtime.close()


def test_classic_answers_initial_evidence_before_expansion(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path / "core")
    run_id = import_pages(runtime, tmp_path, [page()])
    runtime.run_ingest(mode="index_only", run_id=run_id)

    def unwanted(*args):
        pytest.fail("Initial evidence was sufficient; expansion should not run")

    monkeypatch.setattr(runtime.query_pipeline, "_expand_via_graph", unwanted)
    monkeypatch.setattr(runtime.query_pipeline, "_expand_via_section", unwanted)
    assert runtime.query_result("Opening times?").supported
    runtime.close()


def test_robots_redirect_uses_domain_scope_without_content_path_filter():
    fetcher = SafeFetcher(
        redirect_policy=lambda url: "/docs/" in url,
        robots_redirect_policy=lambda url: url.startswith("https://1.1.1.1/"),
    )
    response = SimpleNamespace(status=302, headers=[(b"location", b"/robots-rules")])
    assert fetcher._next("https://1.1.1.1/robots.txt", response, 0, "robots").endswith("/robots-rules")
    with pytest.raises(FetchError):
        fetcher._next("https://1.1.1.1/docs/", response, 0)
    fetcher.close()


def test_pinned_numeric_connection_preserves_original_tls_and_host():
    class Stream(httpcore.NetworkStream):
        tls_hostname = None
        request = b""
        sent = False

        def read(self, max_bytes, timeout=None):
            if self.sent:
                return b""
            self.sent = True
            return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Type: text/html\r\n\r\nok"

        def write(self, buffer, timeout=None):
            self.request += buffer

        def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            self.tls_hostname = server_hostname
            return self

        def close(self):
            pass

        def get_extra_info(self, info):
            return None

    stream = Stream()

    class Backend:
        connected_host = None

        def connect_tcp(self, host, port, **kwargs):
            self.connected_host = host
            return stream

    class Resolver:
        def resolve(self, host, family, **kwargs):
            return ["1.1.1.1"] if family == "A" else []

    fetcher = SafeFetcher(context=OperationContext(limits=OperationLimits(host_interval_s=0)))
    fetcher.sync_pool.close()
    backend = Backend()
    fetcher.sync_pool = httpcore.ConnectionPool(
        network_backend=ValidatingBackend(fetcher.policy, fetcher.context, resolver=Resolver(), backend=backend)
    )
    assert fetcher.fetch("https://example.test/docs") == ("ok", "text/html")
    assert backend.connected_host == "1.1.1.1"
    assert stream.tls_hostname == "example.test"
    assert b"Host: example.test\r\n" in stream.request
    fetcher.close()


def test_pointer_read_retries_only_transient_windows_sharing_errors(tmp_path, monkeypatch):
    store = SnapshotStore(tmp_path)
    (tmp_path / "active.json").write_text('{"version": "valid-version"}', encoding="utf-8")
    original = Path.read_text
    calls = []

    def temporarily_locked(path, *args, **kwargs):
        calls.append(path)
        if len(calls) == 1:
            error = PermissionError("Windows sharing conflict")
            error.winerror = 32
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", temporarily_locked)
    assert store.active_version() == "valid-version" and len(calls) == 2

    def real_permission_failure(*args, **kwargs):
        raise PermissionError("Permission denied")

    monkeypatch.setattr(Path, "read_text", real_permission_failure)
    with pytest.raises(PermissionError):
        store.active_version()


def test_windows_pointer_sharing_error_can_have_only_posix_errno(tmp_path, monkeypatch):
    import errno
    import os

    if os.name != "nt":
        pytest.skip("The errno-only sharing violation is specific to Windows")
    store = SnapshotStore(tmp_path)
    (tmp_path / "active.json").write_text('{"version": "valid-version"}', encoding="utf-8")
    original = Path.read_text
    attempts = []

    def sharing_violation(path, *args, **kwargs):
        attempts.append(path)
        if len(attempts) == 1:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", sharing_violation)
    assert store.active_version() == "valid-version" and len(attempts) == 2


def test_explicit_zero_port_is_not_reinterpreted_as_default_port():
    with pytest.raises(FetchError):
        FetchPolicy().validate_url("https://1.1.1.1:0/")


@pytest.mark.parametrize("mode", ["builder", "classic"])
@pytest.mark.parametrize(
    "html,fact",
    [
        ("<footer><p>Call the visitor desk at 12345.</p></footer>", "Call the visitor desk at 12345."),
        ("<table><tr><td>Engineering</td><td>50000</td></tr></table>", "Engineering | 50000"),
        (
            "<footer><p>يفتح المكتب يوم الثلاثاء الساعة التاسعة.</p></footer>",
            "يفتح المكتب يوم الثلاثاء الساعة التاسعة.",
        ),
    ],
)
def test_new_regions_and_headerless_tables_are_indexed_retrieved_and_cited(tmp_path, html, fact, mode):
    runtime = make_runtime(tmp_path / "core", fact=fact, mode=mode)
    try:
        run_id = import_pages(runtime, tmp_path, [("https://different.test/info", html)])
        result = runtime.run_ingest(mode="index_only", run_id=run_id)
        assert result["indexed"]
        answer = runtime.query_result("Contact information or fees?")
        assert answer.supported and any(fact in c["supporting_span"] for c in answer.citations)
        assert runtime.db.embedding_space["embedding_text_version"] == "blocks-v2"
        records = runtime.db.metadata
        assert any(record["metadata"]["blocks"] for record in records)
    finally:
        runtime.close()


def test_revision_change_invalidates_replay_and_approval_but_reuses_frozen_html(tmp_path, monkeypatch):
    from webly.crawl import runs

    runtime = make_runtime(tmp_path / "core")
    try:
        first = import_pages(runtime, tmp_path, [page(), page("https://example.test/removed")])
        runtime.run_ingest(mode="index_only", run_id=first)
        candidate = import_pages(runtime, tmp_path, [page()])
        context = OperationContext(operation_id="old-transform", limits=OperationLimits.ingest())
        pending = runtime.run_ingest(mode="index_only", run_id=candidate, context=context)
        assert pending["status"] == "approval_required"
        original_manifest = runtime.inspect_run(candidate)
        monkeypatch.setattr(runs, "EXTRACTION_VERSION", "future-test-revision")
        with pytest.raises(PublicationConflict):
            runtime.run_ingest(
                mode="index_only",
                run_id=candidate,
                context=OperationContext(operation_id="old-transform", limits=OperationLimits.ingest()),
            )
        stale = runtime.run_ingest(mode="index_only", run_id=candidate, approval=pending["proposal"]["approval_token"])
        assert stale["status"] == "approval_required"
        assert stale["proposal"]["approval_token"] != pending["proposal"]["approval_token"]
        accepted = runtime.run_ingest(mode="index_only", run_id=candidate, approval=stale["proposal"]["approval_token"])
        assert accepted["indexed"] and runtime.inspect_run(candidate) == original_manifest
    finally:
        runtime.close()


def test_old_extraction_snapshot_and_cache_identity_require_rebuild(tmp_path):
    runtime = make_runtime(tmp_path / "core")
    try:
        run_id = import_pages(runtime, tmp_path, [page()])
        space = runtime.db.embedding_space.copy()
        runtime.db.embedding_space["embedding_text_version"] = "blocks-v1"
        runtime.run_ingest(mode="index_only", run_id=run_id)
        runtime.db.embedding_space = space
        with pytest.raises(ArtifactError):
            runtime.query_result("Opening times?")
        runtime.run_ingest(mode="index_only", run_id=run_id)
        assert runtime.query_result("Opening times?").supported
        assert EmbeddingCache.make_key("fact", "model", preprocessing_version="blocks-v1") != EmbeddingCache.make_key(
            "fact", "model", preprocessing_version="blocks-v2"
        )
    finally:
        runtime.close()
