"""Frozen crawl inputs, reviewed removal diffs and recoverable host operations."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict
from pathlib import Path

from filelock import FileLock

from webly.contracts import (
    ApprovalRequired,
    ArtifactError,
    ConfigurationError,
    CoreError,
    IngestResult,
    OperationOutcome,
    PublicationConflict,
    atomic_json,
    digest_json,
)
from webly.crawl.policy import capture_policy, compatibility, require_compatible
from webly.processors.extraction_version import EXTRACTION_VERSION
from webly.vector_index.snapshots import SnapshotStore


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_inventory(path):
    sources = {}
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
                url, html = record["url"], record["html"]
                if not isinstance(url, str) or not url or not isinstance(html, str) or url in sources:
                    raise ValueError()
                sources[url] = hashlib.sha256(html.encode()).hexdigest()
            except (ValueError, KeyError, TypeError):
                raise ArtifactError("Crawl run contains malformed or repeated page records") from None
    if not sources:
        raise ArtifactError("Crawl run has no captured pages")
    return sources


class CrawlRuns:
    def __init__(self, resources):
        self.resources = resources

    def directory(self, run_id):
        return self.resources.path("runs", run_id)

    def new(self):
        run_id = uuid.uuid4().hex
        root = self.directory(run_id)
        root.mkdir(parents=True)
        atomic_json(root / "run.json", {"format": 1, "run_id": run_id, "status": "running"})
        return run_id

    def seal(self, run_id, *, config, excluded=None, origin="crawl"):
        root = self.directory(run_id)
        source = root / "results.jsonl"
        if not source.is_file() or (root / ".crawl_incomplete").exists():
            raise ArtifactError("Crawl run is missing or incomplete")
        sources = source_inventory(source)
        checksums = {
            name: file_digest(root / name) for name in ("results.jsonl", "graph.json") if (root / name).is_file()
        }
        policy = capture_policy(config)
        manifest = {
            "format": 2,
            "run_id": run_id,
            "status": "completed",
            "checksums": checksums,
            "config_digest": digest_json(config),
            "sources": sources,
            "coverage": {"captured": len(sources), "excluded": excluded or {}, "failed": 0},
            "extractor_version": EXTRACTION_VERSION,
            "crawl_policy": policy,
            "crawl_policy_digest": digest_json(policy),
            "origin": origin,
        }
        require_compatible(manifest, config)
        atomic_json(root / "run.json", manifest)
        return manifest

    def validate(self, run_id):
        root = self.directory(run_id)
        try:
            manifest = json.loads((root / "run.json").read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise ArtifactError("Crawl run manifest is missing or corrupt") from None
        if manifest.get("status") != "completed" or manifest.get("run_id") != run_id:
            raise ArtifactError("Only completed crawl runs may be indexed")
        if (root / ".crawl_incomplete").exists():
            raise ArtifactError("Crawl run is incomplete")
        checksums = manifest.get("checksums", {})
        if "results.jsonl" not in checksums:
            raise ArtifactError("Crawl run checksum manifest is incomplete")
        for name, expected in checksums.items():
            path = self.resources.path("runs", run_id, name)
            if not path.is_file() or file_digest(path) != expected:
                raise ArtifactError("Frozen crawl run changed")
        if manifest.get("sources") != source_inventory(root / "results.jsonl"):
            raise ArtifactError("Run source inventory does not match the frozen records")
        return manifest

    def import_legacy(self, path, *, acknowledge_complete, config):
        if acknowledge_complete is not True:
            raise ConfigurationError("Explicit completeness acknowledgement is required for legacy imports")
        source = Path(path)
        if not source.is_file() or source.is_symlink():
            raise ConfigurationError("Explicit import source must be a regular file")
        run_id = self.new()
        target = self.directory(run_id) / "results.jsonl"
        if source.suffix == ".json":
            data = json.loads(source.read_text(encoding="utf-8-sig"))
            if not isinstance(data, list):
                raise ArtifactError("JSON import must contain an array of page records")
            with target.open("w", encoding="utf-8") as stream:
                for record in data:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        else:
            shutil.copyfile(source, target)
        self.seal(run_id, config=config, origin="trusted_import")
        return run_id

    def inspect(self, run_id, *, config=None):
        path = self.directory(run_id) / "run.json"
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ArtifactError("Run manifest is missing or corrupt") from None
        if manifest.get("status") == "completed":
            manifest = self.validate(run_id)
            if config is not None:
                manifest = {**manifest, "compatibility": compatibility(manifest, config)}
        return manifest


class IngestOperations:
    def __init__(self, runtime):
        self.runtime = runtime
        self.resources = runtime.resources
        self.runs = CrawlRuns(self.resources)

    def execute(self, context, *, mode="both", run_id=None, approval=None, resume=False, force_crawl=False):
        if mode not in {"both", "crawl_only", "index_only"}:
            raise ConfigurationError("Unknown ingest mode")
        record_path = self.resources.path("operations", context.operation_id + ".json")
        record_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(record_path) + ".lock", timeout=max(0.001, context.remaining)):
            original_sink = context.sink
            journal = self.resources.path("operations", context.operation_id + ".events.jsonl")

            def deliver(event):
                entry = {**event, "counters": dict(context._counts)}
                with journal.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                if original_sink:
                    original_sink(event)

            context.sink = deliver
            try:
                return self._execute(record_path, context, mode, run_id, approval, resume)
            finally:
                context.sink = original_sink

    def _execute(self, path, context, mode, run_id, approval, resume):
        runtime, pipe = self.runtime, self.runtime.ingest_pipeline
        config = runtime.config.to_dict()
        fingerprint = digest_json(
            {
                "config": config,
                "mode": mode,
                "run_id": run_id,
                "approval": approval,
                "limits": asdict(context.limits),
                "extraction_version": EXTRACTION_VERSION,
                "crawl_policy_digest": digest_json(capture_policy(config)),
            }
        )
        if path.exists():
            previous = json.loads(path.read_text(encoding="utf-8"))
            if previous["fingerprint"] != fingerprint:
                raise PublicationConflict("Operation ID reused with different inputs")
            store = SnapshotStore(runtime.config.index_dir)
            active = store.active_version()
            if active:
                manifest = json.loads((store.version_path(active) / "manifest.json").read_text())
                if manifest.get("operation_id") == context.operation_id:
                    context.outcome = OperationOutcome("committed", active, context.operation_id)
                    return IngestResult(
                        indexed=True,
                        run_id=previous.get("run_id"),
                        recovered=True,
                        outcome=asdict(OperationOutcome("committed", active, context.operation_id)),
                    )
            if previous.get("status") == "completed":
                result = IngestResult(previous["result"], replayed=True)
                context.outcome = result.outcome
                return result
            if not resume:
                raise PublicationConflict("Interrupted or failed operation requires explicit resume")
            if previous.get("outcome", {}).get("state") == "uncertain":
                raise PublicationConflict("Uncertain publication must be reconciled before retry")
            context._counts.update(previous.get("counts", {}))
            journal = self.resources.path("operations", context.operation_id + ".events.jsonl")
            if journal.is_file():
                for line in journal.read_text(encoding="utf-8").splitlines(keepends=True):
                    if not line.endswith("\n"):
                        continue
                    entry = json.loads(line)
                    context._counts.update(entry.get("counters", {}))
                    context.events.append(entry)
            context._started -= previous.get("elapsed_s", 0)
            run_id = previous.get("run_id", run_id)
            if run_id and mode in {"both", "crawl_only"}:
                try:
                    self.runs.validate(run_id)
                except ArtifactError:
                    run_id = None  # retry into a new run, retaining the failed input
        record = {"fingerprint": fingerprint, "status": "running", "run_id": run_id}
        atomic_json(path, record)
        try:
            context.emit("progress", stage="ingest_started")
            if mode in {"both", "crawl_only"} and not run_id:
                run_id = self.runs.new()
                record["run_id"] = run_id
                atomic_json(path, record)
                root = self.runs.directory(run_id)
                pipe.crawler.output_dir = str(root)
                pipe.crawler.default_settings.update(
                    storage_path=str(root), operation_context=context, max_concurrency=context.limits.concurrency
                )
                pipe.results_path = str(root / "results.jsonl")
                try:
                    pipe.run(mode="crawl_only", force_crawl=True)
                    excluded = getattr(pipe.crawler, "get_disallowed_report", lambda: {})()
                    self.runs.seal(run_id, config=config, excluded=excluded)
                except Exception:
                    atlas = getattr(pipe.crawler, "_atlas", None)
                    atomic_json(
                        root / "run.json",
                        {
                            "format": 1,
                            "run_id": run_id,
                            "status": "failed",
                            "coverage": {
                                "captured": len(getattr(atlas, "graph", {})),
                                "failures": getattr(atlas, "fetch_errors", []),
                            },
                        },
                    )
                    raise
            if not run_id:
                raise ConfigurationError("index_only requires an explicit completed run_id")
            manifest = self.runs.validate(run_id)
            policy_check = require_compatible(manifest, config)
            if mode == "crawl_only":
                result = IngestResult(crawled=True, indexed=False, run_id=run_id, status="completed")
            else:
                pipe.results_path = str(self.runs.directory(run_id) / "results.jsonl")
                pipe.crawler.output_dir = str(self.runs.directory(run_id))

                def guard(records, store):
                    require_compatible(self.runs.validate(run_id), config)
                    active = store.active_version()
                    old = {}
                    if active:
                        old = json.loads((store.version_path(active) / "manifest.json").read_text()).get(
                            "publication", {}
                        )
                    sources = manifest["sources"]
                    previous_sources = old.get("sources", {})
                    removed = sorted(set(previous_sources) - set(sources))
                    proposal = {
                        "run_id": run_id,
                        "expected_version": active,
                        "added": sorted(set(sources) - set(previous_sources)),
                        "removed": removed,
                        "changed": sorted(
                            url for url in set(sources) & set(previous_sources) if sources[url] != previous_sources[url]
                        ),
                        "candidate_digest": digest_json(
                            {
                                "source": manifest,
                                "config": config,
                                "embedding_space": pipe.db.embedding_space,
                                "extraction_version": EXTRACTION_VERSION,
                                "crawl_policy_digest": policy_check["crawl_policy_digest"],
                            }
                        ),
                    }
                    proposal["approval_token"] = digest_json(proposal)
                    if removed and approval != proposal["approval_token"]:
                        raise ApprovalRequired(proposal)
                    pipe.publication_metadata = {
                        "run_id": run_id,
                        "sources": sources,
                        "resource_id": self.resources.resource_id,
                        "candidate_digest": proposal["candidate_digest"],
                        "extraction_version": EXTRACTION_VERSION,
                        "crawl_policy_digest": policy_check["crawl_policy_digest"],
                    }

                pipe.publication_guard = guard
                result = IngestResult(pipe.run(mode="index_only"), run_id=run_id, status="completed")
            result["outcome"] = asdict(context.outcome)
            result["usage"] = context.summary()
            record.update(status="completed", result=result)
            atomic_json(path, record)
            return result
        except ApprovalRequired as exc:
            result = IngestResult(
                indexed=False,
                run_id=run_id,
                status="approval_required",
                proposal=exc.proposal,
                outcome=asdict(context.outcome),
                usage=context.summary(),
            )
            record.update(status="completed", result=result)
            atomic_json(path, record)
            return result
        except Exception as exc:
            if isinstance(exc, CoreError):
                exc.operation_id = context.operation_id
                exc.outcome = context.outcome
            else:
                exc = ArtifactError(
                    f"Ingest failed ({type(exc).__name__})", operation_id=context.operation_id, outcome=context.outcome
                )
            record.update(
                status="failed",
                code=exc.code,
                outcome=asdict(context.outcome),
                counts=context._counts,
                elapsed_s=context.limits.timeout_s - context.remaining,
            )
            try:
                atomic_json(path, record)
            except OSError:
                pass
            raise exc from None
