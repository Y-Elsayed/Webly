"""Offline multi-process, disk-full and restart checks using fixture providers.

No customer roots are used. --small-fs selects an explicitly disposable tmpfs.
"""

import argparse
import errno
import json
import multiprocessing
import os
import platform
import tempfile
import time
from pathlib import Path

from scripts.worker_example import FACT, runtime_for
from webly import OperationContext, OperationLimits
from webly.contracts import CoreError, OperationCancelled, operation_scope
from webly.vector_index.faiss_db import FaissDatabase
from webly.vector_index.snapshots import SnapshotStore


def database(text, space):
    db = FaissDatabase(embedding_space=space)
    db.create(4)
    db.add(
        [
            {
                "segment_id": "fixture",
                "url": "https://fixture.test/",
                "text": text,
                "original_text": text,
                "embedding": [1, 0, 0, 0],
            }
        ]
    )
    return db


def reader(root, ready, stop, queue):
    try:
        runtime = runtime_for(Path(root))
        with runtime.providers, runtime:
            count = 0
            while not stop.is_set():
                answer = runtime.query_result("Opening times?")
                assert answer.supported and answer.citations
                count += 1
                ready.set()
            queue.put({"reader_queries": count})
    except Exception as exc:
        queue.put({"reader_error": type(exc).__name__})
        ready.set()


def writer(root, source, expected, barrier, queue, index):
    runtime = runtime_for(Path(root))
    with runtime.providers, runtime:
        db = database(FACT, runtime.db.embedding_space)
        barrier.wait(timeout=30)
        try:
            with operation_scope(OperationContext()):
                version = SnapshotStore(runtime.config.index_dir).publish(
                    db, expected_version=expected, source_path=source
                )
            queue.put({"writer": index, "state": "committed", "version": version})
        except CoreError as exc:
            queue.put({"writer": index, "state": exc.code})


def crash_after_pointer(root, run):
    original = SnapshotStore._write_pointer

    def crash(self, version):
        original(self, version)
        os._exit(91)

    SnapshotStore._write_pointer = crash
    runtime = runtime_for(Path(root))
    runtime.run_ingest(
        mode="index_only",
        run_id=run,
        context=OperationContext(operation_id="terminated-host", limits=OperationLimits.ingest()),
    )


def setup(root, fact=FACT):
    runtime = runtime_for(root)
    source = root.parent / (root.name + "-source.jsonl")
    source.write_text(json.dumps({"url": "https://fixture.test/", "html": f"<p>{fact}</p>"}) + "\n")
    run = runtime.import_legacy(source, acknowledge_complete=True)
    return runtime, run


def run_checks(root, small_fs=None):
    started = time.monotonic()
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "fixture_providers": True,
        "real_model_calls": False,
        "production_certified": False,
    }
    ctx = multiprocessing.get_context("spawn")
    runtime, run = setup(root / "shared")
    children = []
    with runtime.providers, runtime:
        runtime.run_ingest(mode="index_only", run_id=run)
        cancelled = OperationContext()
        cancelled.cancelled.set()
        try:
            runtime.query_result("Opening times?", context=cancelled)
        except OperationCancelled:
            report["cancellation"] = "passed"
        else:
            raise AssertionError("Cancelled query performed work")
        store = SnapshotStore(runtime.config.index_dir)
        old = store.active_version()
        queue, ready, stop = ctx.Queue(), ctx.Event(), ctx.Event()
        read = ctx.Process(target=reader, args=(str(root / "shared"), ready, stop, queue))
        children.append(read)
        read.start()
        try:
            if not ready.wait(timeout=30):
                raise RuntimeError("Reader did not start")
            barrier = ctx.Barrier(2)
            for i in range(2):
                source = str(runtime.resources.path("runs", run, "results.jsonl"))
                process = ctx.Process(target=writer, args=(str(root / "shared"), source, old, barrier, queue, i))
                children.append(process)
                process.start()
            for process in children[1:]:
                process.join(timeout=45)
                assert process.exitcode == 0, "Writer failed or timed out"
            stop.set()
            read.join(timeout=30)
            assert read.exitcode == 0, "Reader failed or timed out"
            outcomes = [queue.get(timeout=5) for _ in range(3)]
            assert sorted(r["state"] for r in outcomes if "writer" in r) == ["committed", "publication_conflict"]
            assert next(r["reader_queries"] for r in outcomes if "reader_queries" in r) > 0
            store.validate(store.active_version())
            report["reader_writer_contention"] = outcomes
        finally:
            stop.set()
            for process in children:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            queue.close()
        backup = root / "backup"
        runtime.export_snapshot(backup)
    restored = runtime_for(root / "restored")
    with restored.providers, restored:
        restored.restore_snapshot(backup)
        assert restored.query_result("Opening times?").supported
        report["export_restore"] = "passed"

    killed, run = setup(root / "killed")
    killed.close()
    killed.providers.close()
    process = ctx.Process(target=crash_after_pointer, args=(str(root / "killed"), run))
    process.start()
    try:
        process.join(timeout=45)
        assert process.exitcode == 91
    finally:
        if process.is_alive():
            process.terminate()
            process.join()
    reopened = runtime_for(root / "killed")
    with reopened.providers, reopened:
        result = reopened.run_ingest(
            mode="index_only",
            run_id=run,
            context=OperationContext(operation_id="terminated-host", limits=OperationLimits.ingest()),
        )
        assert result.get("recovered") and result.outcome.state == "committed"
        report["process_death_reconciliation"] = "passed"

    if small_fs:
        with tempfile.TemporaryDirectory(prefix="webly-disk-check-", dir=small_fs) as small:
            store = SnapshotStore(Path(small) / "index")
            initial = store.publish(database("Original fact", None))
            try:
                store.publish(database("X" * (2 * 1024 * 1024), None), expected_version=initial)
            except OSError as exc:
                assert exc.errno == errno.ENOSPC
            else:
                raise AssertionError("Small filesystem was not actually exhausted")
            assert store.active_version() == initial
            store.validate(initial)
            report["disk_full"] = "real_enospc_previous_snapshot_valid"
    else:
        report["disk_full"] = "not_measured_requires_disposable_small_filesystem"
    report["elapsed_s"] = round(time.monotonic() - started, 3)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--small-fs", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="webly-host-checks-") as temporary:
        report = run_checks(Path(temporary), args.small_fs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
