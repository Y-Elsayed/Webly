"""Run from the repository root after building a wheel in the audit temp directory.

Requires the API/test dependencies. Uses temporary project data and reads public
PyPI metadata; makes no crawler fetches or model API calls. See the audit report.
"""

import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from webly._webcreeper import Atlas
from webly.chatbot.webly_chat_agent import WeblyChatAgent
from webly.observability.cost_tracker import CostTracker
from webly.processors.text_chunkers import SlidingTextChunker
from webly.service.app import create_app

out = {"date": "2026-11-12", "network_scope": "PyPI metadata only; no private-network or provider requests"}
with tempfile.TemporaryDirectory(prefix="webly-audit-") as temporary:
    root = Path(temporary)
    client = TestClient(create_app(storage_root=str(root / "storage")))
    response = client.post("/v1/projects", json={"name": "client-a", "config": {"start_url": "https://example.test"}})
    out["unauthenticated_create_status"] = response.status_code
    out["unauthenticated_list_status"] = client.get("/v1/projects").status_code
    marker = root / "outside.jsonl"
    marker.write_text("{}\n")
    response = client.post(
        "/v1/projects",
        json={
            "name": "outside-source",
            "config": {"start_url": "https://example.test", "results_file": str(marker)},
        },
    )
    config = client.get("/v1/projects/outside-source").json()["config"]
    out["outside_source_path_accepted"] = response.is_success and Path(config["results_file"]).resolve() == marker
    out["outside_source_reported_ready"] = client.get("/v1/projects/outside-source/status").json()["results_ready"]

    atlas = Atlas(
        settings={"storage_path": str(root / "crawl"), "base_url": "http://127.0.0.1", "respect_robots": False}
    )
    out["private_ip_crawl_policy_allowed"] = atlas.should_visit("http://127.0.0.1/admin")
    out["crawler_has_global_page_limit_setting"] = "max_pages" in atlas.settings
    first = '<p>Identical visible content on both pages.</p><a href="/first">Details</a>'
    second = '<p>Identical visible content on both pages.</p><a href="/second">Details</a>'
    out["crawler_skips_second_page_with_different_link_targets"] = not atlas._is_duplicate_content(
        first, "https://example.test/1"
    ) and atlas._is_duplicate_content(second, "https://example.test/2")

    chunks = SlidingTextChunker().chunk_html(
        "<h1>Admissions</h1><p>Deadline: June 1</p><p>Longer introductory paragraph without the actual deadline.</p>",
        "https://example.test/admissions",
    )
    out["short_fact_lost_when_other_block_exists"] = not any("June" in chunk["text"] for chunk in chunks)

    tracker = CostTracker(str(root / "usage"))
    tracker.record_embedding("test", 10)
    (root / "usage").mkdir()
    (root / "usage" / "usage_log.jsonl").mkdir()
    try:
        tracker.flush()
    except OSError:
        pass
    out["usage_events_remaining_after_failed_flush"] = tracker.totals()["total_tokens"]

    class ScriptedModel:
        context_window_tokens = 128000

        def generate(self, _prompt):
            return json.dumps(
                {
                    "answer": "The fee is 100.",
                    "status": "answered",
                    "citations": [{"segment_id": "a", "supporting_span": "Fee: 100"}],
                    "missing_information": [],
                }
            )

    agent = WeblyChatAgent(None, None, ScriptedModel())
    context = (
        "[Evidence: a] (Source: https://example.test/a)\nIntroduction only.\n\n---\n\n"
        "[Evidence: b] (Source: https://example.test/b)\nFee: 100"
    )
    payload = agent.answer_grounded(
        "What is the fee?",
        context,
        [
            {"chunk_id": "a", "url": "https://example.test/a", "original_text": "Introduction only. Fee: 100"},
            {"chunk_id": "b", "url": "https://example.test/b", "original_text": "Fee: 100"},
        ],
    )
    out["answer_validator_accepts_span_only_shown_under_another_id"] = payload[2] == "answered"

    wheel = next(Path(tempfile.gettempdir()).joinpath("webly-production-audit").glob("webly-*.whl"), None)
    if wheel:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata = archive.read(next(n for n in names if n.endswith(".dist-info/METADATA"))).decode()
            out["wheel"] = {
                "built": True,
                "top_level_crawler_bundled": any(n.startswith("webcreeper/") for n in names),
                "crawler_declared_dependency": any(
                    "webcreeper" in line.lower() for line in metadata.splitlines() if line.startswith("Requires-Dist:")
                ),
                "unused_nested_crawler_bundled": any(n.startswith("webly/webcreeper/") for n in names),
                "client_data_in_wheel": any("websites_storage/" in n for n in names),
                "api_dependencies_optional": 'extra == "api"' in metadata,
            }
            extracted = root / "wheel"
            archive.extractall(extracted)
        probe = subprocess.run(
            [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(extracted)!r}); import webly"],
            cwd=temporary,
            capture_output=True,
            text=True,
            check=False,
        )
        out["wheel"]["isolated_import_exit_code"] = probe.returncode
        out["wheel"]["isolated_import_error"] = probe.stderr.strip().splitlines()[-1] if probe.stderr else None

requirements = []
for line in Path("requirements.txt").read_text().splitlines():
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s]+)", line.strip())
    if match:
        requirements.append(match.groups())


def check_requirement(requirement):
    name, version = requirement
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.load(response)
        return {
            "name": name,
            "version": version,
            "source": url,
            "advisories": [
                {
                    "id": item.get("id"),
                    "aliases": item.get("aliases"),
                    "fixed_in": item.get("fixed_in"),
                    "link": item.get("link"),
                }
                for item in payload.get("vulnerabilities", [])
                if not item.get("withdrawn")
            ],
        }
    except Exception as exc:
        return {"name": name, "version": version, "error": type(exc).__name__}


with ThreadPoolExecutor(max_workers=6) as pool:
    out["direct_pinned_dependency_advisories"] = list(pool.map(check_requirement, requirements))
out["dependency_scan_scope"] = (
    "Exact direct pins in requirements.txt only; excludes filelock>=, transitive packages, "
    "containers, and installed-environment differences. Advisory presence does not establish exploitability."
)
Path("docs/audit").mkdir(exist_ok=True)
Path("docs/audit/2026-11-12-evidence.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
concise = {key: value for key, value in out.items() if key != "direct_pinned_dependency_advisories"}
concise["dependency_scan"] = [
    {"name": item["name"], "advisories": len(item.get("advisories", [])), "error": item.get("error")}
    for item in out["direct_pinned_dependency_advisories"]
]
print(json.dumps(concise, indent=2))
