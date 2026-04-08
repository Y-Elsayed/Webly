import json
from pathlib import Path

import pytest

from webly.observability.cost_tracker import CostTracker


def test_record_embedding_and_totals():
    tracker = CostTracker()
    tracker.record_embedding("text-embedding-3-small", prompt_tokens=500)
    tracker.record_embedding("text-embedding-3-small", prompt_tokens=300)
    t = tracker.totals()
    assert t["embedding_tokens"] == 800
    assert t["total_tokens"] == 800
    assert t["chat_prompt_tokens"] == 0
    assert t["chat_completion_tokens"] == 0


def test_record_chat_and_totals():
    tracker = CostTracker()
    tracker.record_chat("gpt-4o-mini", prompt_tokens=200, completion_tokens=100)
    t = tracker.totals()
    assert t["chat_prompt_tokens"] == 200
    assert t["chat_completion_tokens"] == 100
    assert t["total_tokens"] == 300
    assert t["embedding_tokens"] == 0


def test_mixed_events_totals():
    tracker = CostTracker()
    tracker.record_embedding("text-embedding-3-small", prompt_tokens=400)
    tracker.record_chat("gpt-4o-mini", prompt_tokens=100, completion_tokens=50)
    t = tracker.totals()
    assert t["embedding_tokens"] == 400
    assert t["chat_prompt_tokens"] == 100
    assert t["chat_completion_tokens"] == 50
    assert t["total_tokens"] == 550


def test_flush_writes_jsonl(tmp_path: Path):
    tracker = CostTracker(output_dir=str(tmp_path))
    tracker.record_embedding("model", prompt_tokens=10)
    tracker.flush()

    log_path = tmp_path / "usage_log.jsonl"
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["type"] == "embedding"
    assert event["prompt_tokens"] == 10


def test_flush_clears_events(tmp_path: Path):
    tracker = CostTracker(output_dir=str(tmp_path))
    tracker.record_embedding("model", prompt_tokens=10)
    tracker.flush()
    tracker.flush()  # second flush: no new events

    log_path = tmp_path / "usage_log.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1  # only the first flush wrote a line


def test_flush_appends_across_calls(tmp_path: Path):
    tracker = CostTracker(output_dir=str(tmp_path))
    tracker.record_embedding("model", prompt_tokens=10)
    tracker.flush()
    tracker.record_chat("model", prompt_tokens=20, completion_tokens=5)
    tracker.flush()

    log_path = tmp_path / "usage_log.jsonl"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "embedding"
    assert json.loads(lines[1])["type"] == "chat"


def test_flush_with_no_output_dir_is_noop():
    tracker = CostTracker(output_dir=None)
    tracker.record_embedding("model", prompt_tokens=10)
    tracker.flush()  # should not raise, no file created
    assert tracker.totals()["total_tokens"] == 0  # events cleared


def test_totals_empty_tracker():
    tracker = CostTracker()
    t = tracker.totals()
    assert t["total_tokens"] == 0
