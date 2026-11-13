"""Host-owned resource selection and durable usage delivery; no SaaS identity or paid providers.

python -m scripts.worker_example --root /authorized/test/workspace
Fixture providers deliberately do not measure real answer quality.
"""

import argparse
import json
import re
import sqlite3
import threading
from pathlib import Path

from webly import ModelCapabilities, OperationContext, ProviderBundle, ResourceScope, build_runtime

FACT = "The visitor desk opens every Tuesday at nine."


class Embeddings:
    def count_tokens(self, text):
        return len(text.split())

    def embed(self, text):
        return [1.0, float("Tuesday" in text), 0.0, 0.0]


class Model:
    def count_tokens(self, text):
        return len(text.split())

    def generate(self, prompt):
        if "Task: route" in prompt:
            return json.dumps({"mode": "retrieve_new", "requirements": ["Opening times"]})
        if "Task: assess" in prompt:
            return json.dumps({"coverage": [], "queries": []})
        if "Sufficient?" in prompt:
            return "YES"
        if "Cite only Evidence IDs" in prompt:
            match = re.search(r"\[Evidence: ([^\]]+)\].*?\n(?:\[[^\n]*\]\n)?([^\n]+)", prompt, re.S)
            if match:
                return json.dumps(
                    {
                        "answer": match[2],
                        "status": "answered",
                        "missing_information": [],
                        "citations": [{"segment_id": match[1], "supporting_span": match[2]}],
                    }
                )
        return "SAME"


def fixture_providers(_config=None):
    return ProviderBundle(
        Embeddings(),
        ModelCapabilities("fixture-embedding", 8192, dimensions=4),
        Model(),
        ModelCapabilities("fixture-chat", 128000),
    )


class SQLiteEvents:
    """Example delivery store, not a commercial billing ledger."""

    def __init__(self, path):
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS events (operation_id TEXT, sequence INTEGER, payload TEXT, "
            "PRIMARY KEY(operation_id, sequence))"
        )

    def __call__(self, event):
        payload = json.dumps(event, sort_keys=True)
        identity = event["operation_id"], event["sequence"]
        with self.lock, self.connection:
            old = self.connection.execute(
                "SELECT payload FROM events WHERE operation_id=? AND sequence=?", identity
            ).fetchone()
            if old and old[0] != payload:
                raise ValueError("Event identity reused with different contents")
            self.connection.execute("INSERT OR IGNORE INTO events VALUES (?, ?, ?)", (*identity, payload))

    def close(self):
        self.connection.close()


def runtime_for(root, resource_id="example"):
    return build_runtime(
        {"start_url": "https://fixture.test/", "retrieval_mode": "classic", "score_threshold": 0},
        resources=ResourceScope(resource_id, root),
        providers=fixture_providers(),
    )


def main():
    from webly import OperationLimits

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    events = SQLiteEvents(args.root / "events.sqlite")
    try:
        runtime = runtime_for(args.root / "resource")
        with runtime.providers, runtime:
            source = args.root / "capture.jsonl"
            source.write_text(json.dumps({"url": "https://fixture.test/", "html": f"<p>{FACT}</p>"}) + "\n")
            if not runtime.index_exists():
                run = runtime.import_legacy(source, acknowledge_complete=True)
                runtime.run_ingest(
                    mode="index_only",
                    run_id=run,
                    context=OperationContext(limits=OperationLimits.ingest(), sink=events),
                )
            answer = runtime.query_result("Opening times?", context=OperationContext(sink=events))
            assert answer.supported
            print(json.dumps(answer.to_dict(), ensure_ascii=False, indent=2))
    finally:
        events.close()


if __name__ == "__main__":
    main()
