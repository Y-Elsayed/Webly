"""
SQLite-backed embedding cache.

Keyed by blake2b(text + model_name) so the same text embedded with a
different model produces a different cache entry.  The cache is optional
and off by default — pass ``embedding_cache_dir`` in PipelineConfig to
enable it.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone


class EmbeddingCache:
    """Thread-safe SQLite cache for embedding vectors."""

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS embeddings (
        key      TEXT PRIMARY KEY,
        vector   TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """

    def __init__(self, db_path: str) -> None:
        parent = os.path.dirname(db_path) or "."
        os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(self._CREATE_SQL)
        self._conn.commit()

    @staticmethod
    def make_key(text: str, model_name: str) -> str:
        """Deterministic cache key for a (text, model) pair."""
        payload = (text + "\x00" + model_name).encode("utf-8")
        return hashlib.blake2b(payload, digest_size=16).hexdigest()

    def get(self, key: str) -> list[float] | None:
        """Return the cached vector, or None on a cache miss."""
        cur = self._conn.execute("SELECT vector FROM embeddings WHERE key = ?", (key,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, vector: list[float]) -> None:
        """Store a vector under the given key."""
        self._conn.execute(
            "INSERT OR REPLACE INTO embeddings (key, vector, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(vector), datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
