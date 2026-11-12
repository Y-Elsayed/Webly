"""
Thread-safe API cost tracker.

Records token usage from OpenAI embedding and chat completion calls.
Optionally flushes events to ``{output_dir}/usage_log.jsonl`` for
persistent cost auditing.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from filelock import FileLock


class CostTracker:
    """Collects token-usage events and optionally persists them to JSONL."""

    def __init__(self, output_dir: str | None = None) -> None:
        self._events: list[dict[str, Any]] = []
        self._output_dir = output_dir
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_embedding(self, model: str, prompt_tokens: int, text_count: int = 1) -> None:
        """Record token usage from an embedding API call."""
        event = {
            "event_id": uuid.uuid4().hex,
            "type": "embedding",
            "model": model,
            "prompt_tokens": prompt_tokens,
            "total_tokens": prompt_tokens,
            "text_count": text_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._events.append(event)

    def record_chat(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Record token usage from a chat completion API call."""
        event = {
            "event_id": uuid.uuid4().hex,
            "type": "chat",
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._events.append(event)

    # ── Aggregation ───────────────────────────────────────────────────────────

    def totals(self) -> dict[str, int]:
        """Return summed token counts across all recorded events."""
        embedding_tokens = 0
        chat_prompt_tokens = 0
        chat_completion_tokens = 0

        with self._lock:
            snapshot = list(self._events)

        for ev in snapshot:
            if ev["type"] == "embedding":
                embedding_tokens += ev["prompt_tokens"]
            elif ev["type"] == "chat":
                chat_prompt_tokens += ev["prompt_tokens"]
                chat_completion_tokens += ev["completion_tokens"]

        return {
            "embedding_tokens": embedding_tokens,
            "chat_prompt_tokens": chat_prompt_tokens,
            "chat_completion_tokens": chat_completion_tokens,
            "total_tokens": embedding_tokens + chat_prompt_tokens + chat_completion_tokens,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def flush(self) -> None:
        """Append all pending events to usage_log.jsonl and clear the buffer.

        No-op if ``output_dir`` was not set.
        Lock is released before file I/O so other threads are not blocked.
        """
        if self._output_dir is None:
            with self._lock:
                self._events.clear()
            return

        with self._flush_lock:
            with self._lock:
                batch = list(self._events)
            if not batch:
                return
            os.makedirs(self._output_dir, exist_ok=True)
            log_path = os.path.join(self._output_dir, "usage_log.jsonl")
            with FileLock(log_path + ".lock"), open(log_path, "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in batch))
                f.flush()
                os.fsync(f.fileno())
            with self._lock:
                del self._events[: len(batch)]
