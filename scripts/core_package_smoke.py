"""Installed-package contract test; run with `python -I /absolute/path/to/this.py`.

Uses a loopback fixture server and deterministic provider doubles. Never contacts
a model provider. This is package integration evidence, not a quality benchmark.
"""

import importlib.abc
import importlib.metadata
import json
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

OPTIONAL = {"streamlit", "fastapi", "torch", "sentence_transformers", "transformers"}


class RejectOptionalImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in OPTIONAL:
            raise AssertionError(f"Core imported optional dependency: {fullname}")
        return None


sys.meta_path.insert(0, RejectOptionalImports())

import webcreeper  # noqa: E402
import webly  # noqa: E402
from webly.vector_index.snapshots import SnapshotStore  # noqa: E402

FACT = "The observatory opens every Tuesday at nine in the morning."
DETAIL = "The visitor desk accepts reservations by telephone during business hours."


class FixtureSite(BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        self.seen.append(self.path)
        bodies = {
            "/": f'<h1>Observatory</h1><p>{FACT}</p><a href="/visits">Visitor reservations</a>',
            "/visits": f"<h1>Reservations</h1><p>{DETAIL}</p>",
        }
        body = bodies.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        encoded = (body or "Not found").encode()
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        pass


class FixtureEmbedder:
    dim = 4
    max_input_tokens = 8192

    def __init__(self, **_kwargs):
        pass

    def count_tokens(self, text):
        return len(text.encode())

    def embed(self, text):
        return [1.0, float("Tuesday" in text), float("reservations" in text), 0.0]


class FixtureModel:
    context_window_tokens = 128000

    def __init__(self, **_kwargs):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        if "Sufficient?" in prompt:
            return "YES" if FACT in prompt else "NO"
        if "Cite only Evidence IDs above" in prompt:
            blocks = re.findall(r"\[Evidence: ([^\]]+)\](.*?)(?=\[Evidence: |\Z)", prompt, flags=re.DOTALL)
            segment_id = next(sid for sid, text in blocks if FACT in text)
            return json.dumps(
                {
                    "answer": FACT,
                    "status": "answered",
                    "missing_information": [],
                    "citations": [{"segment_id": segment_id, "supporting_span": FACT}],
                }
            )
        raise AssertionError(f"Unexpected provider request: {prompt[:100]}")


def main():
    # -I removes checkout/PYTHONPATH leakage; also verify both imports came from
    # this virtual environment rather than an editable/source installation.
    for module in (webly, webcreeper):
        assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), module.__file__
    assert importlib.metadata.version("webcreeper") == "0.2.0"
    for name in ("streamlit", "fastapi", "torch", "sentence-transformers", "transformers"):
        try:
            importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        raise AssertionError(f"Core-only installation included optional dependency: {name}")
    for name in webly.__all__:
        assert getattr(webly, name) is not None, name
    prompts = Path(webly.__file__).parent / "chatbot" / "prompts"
    for name in ("context_builder_agent.txt", "webly_chat_agent_system.txt"):
        assert (prompts / name).read_text(encoding="utf-8").strip(), name

    with tempfile.TemporaryDirectory(prefix="webly-core-smoke-") as temporary:
        root = Path(temporary)
        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureSite)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            config = {
                "start_url": base_url + "/",
                "allowed_domains": ["127.0.0.1"],
                "output_dir": str(root / "crawl"),
                "index_dir": str(root / "index"),
                "respect_robots": False,
                "crawl_entire_site": False,
                "max_depth": 1,
                "retrieval_mode": "classic",
                "score_threshold": 0.0,
            }
            with (
                patch("webly.embedder.openai_embedder.OpenAIEmbedder", FixtureEmbedder),
                patch("webly.runtime.ChatGPTModel", FixtureModel),
            ):
                runtime = webly.build_runtime(config, api_key="fixture-not-a-real-key")
                ingest = runtime.run_ingest(mode="both")
                assert ingest["indexed"], ingest
                assert ingest["ingest_summary"]["pages_indexed"] == 2, ingest
                assert {"/", "/visits"}.issubset(FixtureSite.seen), FixtureSite.seen
                records = [json.loads(line) for line in (root / "crawl" / "results.jsonl").read_text().splitlines()]
                expected_urls = {base_url + "/", base_url + "/visits"}
                assert {record["url"] for record in records} == expected_urls

                reopened = webly.build_runtime(webly.ProjectConfig.from_dict(config), api_key="fixture-not-a-real-key")
                assert reopened.ensure_index_loaded()
                version = SnapshotStore(config["index_dir"]).active_version()
                assert version
                metadata = reopened.db.metadata
                assert {item["url"] for item in metadata} == expected_urls
                assert all(item["page_version_id"] and item["segment_id"] for item in metadata)
                result = reopened.query_result("When does the observatory open?")
                assert isinstance(result, webly.QueryResult)
                assert result.supported and result.answer == FACT, result.to_dict()
                assert result.trace["index_version"] == version
                assert any(source.url == base_url + "/" for source in result.sources), result.to_dict()
                assert result.citations and all(c["page_url"] in expected_urls for c in result.citations)
                assert all(c["segment_id"] in {m["segment_id"] for m in metadata} for c in result.citations)
                assert result.to_dict()["status"] == "answered"
                ingest_pipe, query_pipe = webly.build_pipelines(config, api_key="fixture-not-a-real-key")
                assert isinstance(ingest_pipe, webly.IngestPipeline)
                assert isinstance(query_pipe, webly.QueryPipeline)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    assert not OPTIONAL.intersection(sys.modules)
    print("Core package contract passed: real crawl, publish, reopen, grounded query; optional imports blocked.")


if __name__ == "__main__":
    main()
