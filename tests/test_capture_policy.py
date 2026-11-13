import json
from dataclasses import fields

import pytest
from test_core_v2 import import_pages, make_runtime, page

from webcreeper.creeper_core.scope import domain_allowed, normalize_url_identity, scope_allowed
from webly.contracts import ArtifactError, RunPolicyMismatch, digest_json
from webly.crawl.policy import CAPTURE_FIELDS, NON_CAPTURE_FIELDS, capture_policy
from webly.project_config import ProjectConfig


@pytest.mark.parametrize(
    "field,value",
    [
        ("start_url", "https://other.test/"),
        ("allowed_domains", ["example.test", "other.test"]),
        ("allowed_paths", ["/"]),
        ("blocked_paths", ["/private"]),
        ("allow_url_patterns", ["example"]),
        ("block_url_patterns", ["private"]),
        ("allow_subdomains", True),
        ("seed_urls", ["https://example.test/"]),
        ("crawl_entire_site", False),
        ("max_depth", 4),
        ("respect_robots", False),
    ],
)
def test_capture_changes_rejected_before_embedding_and_cannot_be_approved(tmp_path, field, value):
    with make_runtime(tmp_path / "core") as runtime:
        run = import_pages(runtime, tmp_path, [page()])
        before = runtime.inspect_run(run)
        setattr(runtime.config, field, value)
        assert not runtime.inspect_run(run)["compatibility"]["compatible"]
        with pytest.raises(RunPolicyMismatch) as error:
            runtime.run_ingest(mode="index_only", run_id=run, approval="cannot-bypass")
        assert field in error.value.changed_fields
        assert error.value.outcome.state == "not_committed" and runtime.providers.embedder.calls == 0
        assert not runtime.index_exists()
        assert runtime.resources.path("runs", run, "run.json").read_text()
        assert before["origin"] == "trusted_import"


def test_new_runs_allow_non_capture_changes_and_report_published_identity(tmp_path):
    with make_runtime(tmp_path / "core") as runtime:
        run = import_pages(runtime, tmp_path, [page()])
        before = runtime.resources.path("runs", run, "run.json").read_bytes()
        runtime.config.retrieval_mode = "builder"
        runtime.config.score_threshold = 0.2
        runtime.config.rate_limit_delay = 1
        assert runtime.inspect_run(run)["compatibility"]["compatible"]
        runtime.run_ingest(mode="index_only", run_id=run)
        answer = runtime.query_result("Opening times?")
        assert answer.trace["crawl_policy_digest"] == digest_json(capture_policy(runtime.config.to_dict()))
        assert runtime.resources.path("runs", run, "run.json").read_bytes() == before


def test_legacy_runs_require_exact_full_config_and_valid_sources(tmp_path):
    with make_runtime(tmp_path / "core") as runtime:
        run = import_pages(runtime, tmp_path, [page()])
        path = runtime.resources.path("runs", run, "run.json")
        manifest = json.loads(path.read_text())
        manifest["format"] = 1
        for key in ("crawl_policy", "crawl_policy_digest", "origin"):
            manifest.pop(key)
        path.write_text(json.dumps(manifest), encoding="utf-8")
        original = path.read_bytes()
        assert runtime.inspect_run(run)["compatibility"]["compatible"]
        runtime.run_ingest(mode="index_only", run_id=run)
        runtime.config.score_threshold = 0.1
        with pytest.raises(RunPolicyMismatch):
            runtime.run_ingest(mode="index_only", run_id=run)
        assert path.read_bytes() == original


def test_out_of_scope_import_and_inventory_tampering_fail(tmp_path):
    with make_runtime(tmp_path / "core") as runtime:
        with pytest.raises(RunPolicyMismatch):
            import_pages(runtime, tmp_path, [page("https://outside.test/")])
        run = import_pages(runtime, tmp_path, [page()])
        path = runtime.resources.path("runs", run, "run.json")
        data = json.loads(path.read_text())
        data["sources"] = {}
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ArtifactError):
            runtime.run_ingest(mode="index_only", run_id=run)
        assert runtime.providers.embedder.calls == 0


def test_final_guard_rechecks_compatibility_after_transformation(tmp_path, monkeypatch):
    with make_runtime(tmp_path / "core") as runtime:
        run = import_pages(runtime, tmp_path, [page()])
        original = runtime.ingest_pipeline.transform

        def tamper():
            records = original()
            path = runtime.resources.path("runs", run, "run.json")
            data = json.loads(path.read_text())
            data["crawl_policy"]["max_depth"] = 99
            data["crawl_policy_digest"] = digest_json(data["crawl_policy"])
            path.write_text(json.dumps(data), encoding="utf-8")
            return records

        monkeypatch.setattr(runtime.ingest_pipeline, "transform", tamper)
        with pytest.raises(RunPolicyMismatch):
            runtime.run_ingest(mode="index_only", run_id=run)
        assert not runtime.index_exists()


def test_policy_is_canonical_and_all_config_fields_are_classified(tmp_path):
    assert set(CAPTURE_FIELDS) | NON_CAPTURE_FIELDS == {f.name for f in fields(ProjectConfig)}
    with make_runtime(tmp_path / "core") as runtime:
        config = runtime.config.to_dict()
        config["allowed_domains"] = ["WWW.EXAMPLE.test", "example.test"]
        first = capture_policy(config)
        config["allowed_domains"] = ["example.test"]
        assert capture_policy(config) == first
    assert normalize_url_identity("HTTPS://Example.test/?page=2&x=1#top") == "https://example.test/?page=2&x=1"
    assert domain_allowed("https://outside.test/", {"base_url": "https://example.test/"}) is False
    assert (
        scope_allowed(
            "https://example.test/private", {"start_url": "https://example.test/", "blocked_paths": ["/private"]}
        )
        is False
    )
    assert not scope_allowed("https://user:secret@example.test/", {})
