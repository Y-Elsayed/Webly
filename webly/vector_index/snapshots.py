"""Immutable local FAISS snapshots with an atomic active-version pointer."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from filelock import FileLock

from webly.vector_index.faiss_db import FaissDatabase


class SnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def active_version(self) -> str | None:
        pointer = self.root / "active.json"
        if not pointer.exists():
            return None
        data = json.loads(pointer.read_text(encoding="utf-8"))
        version = data.get("version")
        if not isinstance(version, str) or not version or Path(version).name != version:
            raise RuntimeError("Invalid active snapshot pointer")
        return version

    def version_path(self, version: str) -> Path:
        if Path(version).name != version or version.startswith("."):
            raise ValueError("Invalid snapshot version")
        return self.root / "versions" / version

    @staticmethod
    def _digest(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    @staticmethod
    def _sync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def validate(self, version: str, *, embedding_space: dict | None = None) -> Path:
        path = self.version_path(version)
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format") != 1 or manifest.get("version") != version:
            raise RuntimeError("Incompatible snapshot manifest")
        if embedding_space is not None and manifest.get("embedding_space") != embedding_space:
            raise RuntimeError("Embedding space mismatch; rebuild required")
        checksums = manifest.get("checksums")
        if not isinstance(checksums, dict) or not {"embeddings.index", "metadata.json"} <= set(checksums):
            raise RuntimeError("Snapshot manifest is incomplete")
        for name, expected in checksums.items():
            if name != Path(name).name or self._digest(path / name) != expected:
                raise RuntimeError(f"Snapshot artifact checksum mismatch: {name}")
        db = FaissDatabase(str(path), embedding_space=embedding_space)
        if db.index.ntotal != manifest["segment_count"]:
            raise RuntimeError("Snapshot segment count mismatch")
        return path

    def publish(
        self,
        db: FaissDatabase,
        *,
        source_path: str | None = None,
        expected_source_digest: str | None = None,
        expected_version: str | None = None,
    ) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        versions = self.root / "versions"
        versions.mkdir(exist_ok=True)
        lock_path = self.root / ".publish.lock"
        with FileLock(str(lock_path)):
            if self.active_version() != expected_version:
                raise RuntimeError("Active snapshot changed during build")
            version = uuid.uuid4().hex
            staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=versions))
            try:
                db.save(str(staging))
                files = ["embeddings.index", "metadata.json"]
                if source_path:
                    shutil.copyfile(source_path, staging / "results.jsonl")
                    if expected_source_digest and self._digest(staging / "results.jsonl") != expected_source_digest:
                        raise RuntimeError("Crawl results changed during snapshot copy")
                    files.append("results.jsonl")
                    graph = Path(source_path).with_name("graph.json")
                    if graph.is_file():
                        shutil.copyfile(graph, staging / "graph.json")
                        files.append("graph.json")
                checksums = {name: self._digest(staging / name) for name in files}
                manifest = {
                    "format": 1,
                    "version": version,
                    "embedding_space": db.embedding_space,
                    "segment_count": db.index.ntotal,
                    "checksums": checksums,
                }
                with (staging / "manifest.json").open("w", encoding="utf-8") as stream:
                    json.dump(manifest, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                for name in files:
                    with (staging / name).open("rb") as stream:
                        os.fsync(stream.fileno())
                self._sync_directory(staging)
                final = self.version_path(version)
                os.replace(staging, final)
                self._sync_directory(versions)
                self.validate(version, embedding_space=db.embedding_space)
                self._write_pointer(version)
                return version
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

    def rollback(self, version: str, *, expected_version: str, embedding_space: dict | None = None) -> None:
        with FileLock(str(self.root / ".publish.lock")):
            if self.active_version() != expected_version:
                raise RuntimeError("Active snapshot changed before rollback")
            self.validate(version, embedding_space=embedding_space)
            self._write_pointer(version)

    def _write_pointer(self, version: str) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".active-", dir=self.root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"version": version}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.root / "active.json")
            self._sync_directory(self.root)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
