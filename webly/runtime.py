from __future__ import annotations

import json
import os
import shutil
import sys
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from webly._webcreeper import configure_logging
from webly.chatbot.prompts.system_prompts import apply_mode_flags, get_system_prompt
from webly.chatbot.webly_chat_agent import WeblyChatAgent
from webly.contracts import (
    ArtifactError,
    BudgetExceeded,
    ConfigurationError,
    IngestResult,
    OperationContext,
    OperationLimits,
    ResourceScope,
    UsageDeliveryError,
    operation_scope,
)
from webly.crawl.crawler import Crawler
from webly.observability.cost_tracker import CostTracker
from webly.pipeline.ingest_pipeline import IngestPipeline
from webly.pipeline.query_pipeline import QueryPipeline
from webly.processors.extraction_version import EXTRACTION_VERSION
from webly.project_config import ProjectConfig
from webly.providers import AccountedProvider, ProviderBundle
from webly.query_result import QueryResult
from webly.vector_index.faiss_db import FaissDatabase
from webly.vector_index.snapshots import SnapshotStore


@dataclass(slots=True)
class ProjectRuntime:
    config: ProjectConfig
    ingest_pipeline: IngestPipeline
    query_pipeline: QueryPipeline | None
    cost_tracker: CostTracker
    resources: ResourceScope | None = None
    providers: ProviderBundle | None = field(default=None, repr=False)
    _closed: bool = field(default=False, repr=False)
    _owns_providers: bool = field(default=False, repr=False)
    _query_lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _loaded_version: str | None = None

    def close(self):
        with self._query_lock:
            if self._closed:
                return
            self._closed = True
            close = getattr(getattr(self.ingest_pipeline, "crawler", None), "close", None)
            if close:
                close()
            cache = getattr(getattr(self.ingest_pipeline, "embedder", None), "cache", None)
            if cache:
                cache.close()
            if self._owns_providers and self.providers:
                self.providers.close()
            if self.query_pipeline:
                self.query_pipeline._query_state.set({})

    def import_legacy(self, path, *, acknowledge_complete=False):
        self._check_open()
        from webly.crawl.runs import CrawlRuns

        if not self.resources:
            raise ConfigurationError("Explicit resources are required")
        return CrawlRuns(self.resources).import_legacy(
            path, acknowledge_complete=acknowledge_complete, config=self.config.to_dict()
        )

    def inspect_run(self, run_id):
        from webly.crawl.runs import CrawlRuns

        self._check_open()
        return CrawlRuns(self.resources).inspect(run_id)

    def export_snapshot(self, destination):
        self._check_open()
        with self._query_lock:
            store = SnapshotStore(self.config.index_dir)
            version = store.active_version()
            if not version:
                raise ConfigurationError("No active snapshot to export")
            source = store.validate(version, embedding_space=self.db.embedding_space)
            target = Path(destination)
            if target.exists():
                raise ConfigurationError("Export destination must not already exist")
            shutil.copytree(source, target / "versions" / version)
            from webly.contracts import atomic_json

            atomic_json(target / "active.json", {"version": version})
            atomic_json(target / "resource.json", {"format": 1, "resource_id": self.resources.resource_id})
            return version

    def restore_snapshot(self, source, *, context=None):
        self._check_open()
        source = Path(source)
        if json.loads((source / "resource.json").read_text()) != {
            "format": 1,
            "resource_id": self.resources.resource_id,
        }:
            raise ConfigurationError("Backup resource identity mismatch")
        target = SnapshotStore(self.config.index_dir)
        if target.active_version():
            raise ConfigurationError("Restore requires an empty scope; replacement requires a reviewed build")
        backup = SnapshotStore(source)
        version = backup.active_version()
        db = backup.validate(version, embedding_space=self.db.embedding_space, load_db=True)
        root = backup.version_path(version)
        manifest = json.loads((root / "manifest.json").read_text())
        context = context or OperationContext(limits=OperationLimits.ingest())
        with self._query_lock, operation_scope(context):
            published = target.publish(
                db,
                source_path=str(root / "results.jsonl"),
                expected_source_digest=manifest["checksums"]["results.jsonl"],
                metadata=manifest["publication"],
            )
            self._loaded_version = None
            return published

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *_exc):
        self.close()

    def _check_open(self):
        if self._closed or (self.providers is not None and self.providers._closed):
            raise ConfigurationError("Runtime or provider bundle is closed")

    def _flush_tracker(self, context):
        original = sys.exc_info()[1]
        try:
            self.cost_tracker.flush()
        except Exception:
            context.emit("diagnostic", code="usage_flush_failed")
            if original is None:
                raise UsageDeliveryError(
                    "Usage is pending delivery", operation_id=context.operation_id, outcome=context.outcome
                ) from None

    @contextmanager
    def _operation_lock(self, context):
        if not self._query_lock.acquire(timeout=context.remaining):
            raise BudgetExceeded("Runtime is busy beyond the operation deadline", operation_id=context.operation_id)
        try:
            self._check_open()
            with operation_scope(context):
                yield
        finally:
            self._query_lock.release()

    @property
    def db(self):
        return self.ingest_pipeline.db

    def index_exists(self) -> bool:
        return SnapshotStore(self.config.index_dir).active_version() is not None

    def ensure_index_loaded(self) -> bool:
        store = SnapshotStore(self.config.index_dir)
        version = store.active_version()
        if version is None:
            if os.path.exists(os.path.join(self.config.index_dir, "embeddings.index")):
                raise RuntimeError("Legacy index cannot be used; rebuild from saved crawl results")
            return False
        if self._loaded_version == version:
            return True
        candidate = store.validate(version, embedding_space=self.db.embedding_space, load_db=True)
        self.ingest_pipeline.db = candidate
        if self.query_pipeline is not None:
            self.query_pipeline.chat_agent.vector_db = candidate
            self.query_pipeline.retriever.chat_agent.vector_db = candidate
            self.query_pipeline.retriever._bm25_ready = False
        self._loaded_version = version
        return True

    def run_ingest(self, *, context: OperationContext | None = None, **kwargs):
        self._check_open()
        context = context or OperationContext(limits=OperationLimits.ingest())
        with self._operation_lock(context):
            with operation_scope(context):
                try:
                    if self.resources:
                        from webly.crawl.runs import IngestOperations

                        result = IngestOperations(self).execute(context, **kwargs)
                    else:
                        result = self.ingest_pipeline.run(**kwargs)
                    if self.resources:
                        result = IngestResult(
                            result,
                            operation_id=context.operation_id,
                            outcome=result.get("outcome", asdict(context.outcome)),
                            usage=result.get("usage", context.summary()),
                        )
                    return result
                finally:
                    self._loaded_version = None
                    self._flush_tracker(context)

    def query(self, question: str, *, retry_on_empty: bool = False, memory_context: str = "") -> str:
        return self.query_result(
            question,
            retry_on_empty=retry_on_empty,
            memory_context=memory_context,
        ).answer

    def query_result(
        self,
        question: str,
        *,
        retry_on_empty: bool = False,
        memory_context: str = "",
        context: OperationContext | None = None,
    ) -> QueryResult:
        self._check_open()
        if self.query_pipeline is None:
            raise RuntimeError("Query pipeline is unavailable for this runtime.")
        context = context or OperationContext()
        with self._operation_lock(context):
            try:
                ready = self.ensure_index_loaded()
            except (OSError, ValueError, RuntimeError):
                if self.resources:
                    raise ArtifactError(
                        "Index is incompatible or failed validation", operation_id=context.operation_id
                    ) from None
                raise
            if not ready:
                if self.resources:
                    raise ArtifactError("No active index", operation_id=context.operation_id)
                raise FileNotFoundError(f"No index found at {self.config.index_dir}")
            try:
                result = self.query_pipeline.query_result(
                    question,
                    retry_on_empty=retry_on_empty,
                    memory_context=memory_context,
                )
                result.trace["index_version"] = self._loaded_version
                result.trace["operation_id"] = context.operation_id
                result.trace["usage"] = context.summary()
                if self.resources and not self.config.query_debug:
                    safe = {
                        "index_version",
                        "operation_id",
                        "usage",
                        "mode",
                        "stop_reason",
                        "answer_path",
                        "search_count",
                        "initial_result_count",
                        "combined_result_count",
                    }
                    result.trace = {key: value for key, value in result.trace.items() if key in safe}
                return result
            finally:
                self._flush_tracker(context)


def build_runtime(
    config: Mapping[str, Any] | ProjectConfig, *, resources: ResourceScope, providers: ProviderBundle, fetch_policy=None
) -> ProjectRuntime:
    configure_logging("webly")
    if not isinstance(resources, ResourceScope) or not isinstance(providers, ProviderBundle) or providers._closed:
        raise ConfigurationError("Explicit open resources and providers are required")
    raw = config.to_dict() if isinstance(config, ProjectConfig) else dict(config)
    if raw.get("results_file", "results.jsonl") != "results.jsonl" or raw.get("embedding_cache_dir"):
        raise ConfigurationError("Artifact paths belong to ResourceScope")
    if not isinstance(config, ProjectConfig) and any(raw.get(name) for name in ("output_dir", "index_dir")):
        raise ConfigurationError("Storage paths belong to ResourceScope")
    raw["embedding_model"] = providers.embedding.model_id
    if providers.generation:
        raw["chat_model"] = providers.generation.model_id
    project_config = ProjectConfig.from_dict(
        raw, output_dir=str(resources.path("working")), index_dir=str(resources.path("index"))
    )
    tracker = CostTracker()
    embedder = AccountedProvider(providers.embedder, providers.embedding, "embedding")

    embedding_space = {
        "provider_model": project_config.embedding_model,
        "dimensions": embedder.dim,
        "distance": "normalized_inner_product",
        "embedding_text_version": EXTRACTION_VERSION,
        "provider_endpoint": providers.embedding.endpoint_id,
        "model_revision": providers.embedding.revision,
    }
    db = FaissDatabase(embedding_space=embedding_space)
    chatbot = AccountedProvider(providers.chat, providers.generation, "chat") if providers.chat is not None else None

    summarizer = None
    if providers.summary is not None:
        from webly.processors.text_summarizer import TextSummarizer

        summary_llm = AccountedProvider(providers.summary, providers.summarization, "summary")
        summarizer = TextSummarizer(
            llm=summary_llm,
            prompt_template="Summarize the following webpage clearly:\n\n{text}",
        )

    crawler = Crawler(
        start_url=project_config.start_url,
        allowed_domains=project_config.allowed_domains,
        output_dir=project_config.output_dir,
        results_filename=project_config.results_file,
        default_settings={
            "fetch_policy": fetch_policy,
            "crawl_entire_website": project_config.crawl_entire_site,
            "max_depth": int(project_config.max_depth),
            "allowed_paths": project_config.allowed_paths,
            "blocked_paths": project_config.blocked_paths,
            "allow_url_patterns": project_config.allow_url_patterns,
            "block_url_patterns": project_config.block_url_patterns,
            "allow_subdomains": bool(project_config.allow_subdomains),
            "respect_robots": bool(project_config.respect_robots),
            "rate_limit_delay": float(project_config.rate_limit_delay),
            "seed_urls": project_config.seed_urls,
        },
    )

    ingest_pipeline = IngestPipeline(
        crawler=crawler,
        index_path=project_config.index_dir,
        embedder=embedder,
        db=db,
        summarizer=summarizer,
        use_summary=bool(summarizer),
        debug=bool(project_config.debug),
    )
    ingest_pipeline.cost_tracker = tracker

    query_pipeline = None
    if chatbot is not None:
        configured_system_prompt = get_system_prompt(
            project_config.answering_mode,
            project_config.system_prompt,
            bool(project_config.system_prompt_custom_override),
        )
        configured_system_prompt = apply_mode_flags(
            project_config.answering_mode,
            configured_system_prompt,
            bool(project_config.allow_generated_examples),
        )
        agent = WeblyChatAgent(embedder, db, chatbot, system_prompt=configured_system_prompt)
        query_pipeline = QueryPipeline(
            chat_agent=agent,
            debug=bool(project_config.query_debug),
            allow_best_effort=True,
            retrieval_mode=str(project_config.retrieval_mode),
            builder_max_rounds=int(project_config.builder_max_rounds),
            score_threshold=float(project_config.score_threshold),
        )

    from webly.embedder.embedding_cache import EmbeddingCache

    embedder.cache = EmbeddingCache(str(resources.path("cache", "embeddings.sqlite")))
    embedder.cache_namespace = resources.resource_id
    return ProjectRuntime(
        config=project_config,
        ingest_pipeline=ingest_pipeline,
        query_pipeline=query_pipeline,
        cost_tracker=tracker,
        resources=resources,
        providers=providers,
    )
