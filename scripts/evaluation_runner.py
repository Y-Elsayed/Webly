"""Trusted Core evaluation runner. Setup and queries share the USD reservation sink.

WEBLY_EVAL_CONFIG selects a local JSON configuration; nothing runs on import.
run_case.prepare is invoked only by evaluate_core's explicit --execute phase.
"""

import importlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from webly import OperationContext, OperationLimits, ResourceScope, build_runtime
from webly.contracts import ConfigurationError, atomic_json, digest_json
from webly.crawl.runs import file_digest


def configuration():
    path = Path(os.environ["WEBLY_EVAL_CONFIG"]).resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    config["base"] = path.parent
    return config


def openai_providers(config):
    from webly.adapters import application_providers

    if not config.get("embedding_model") or not config.get("chat_model"):
        raise ConfigurationError("Evaluation models must be explicitly selected")
    return application_providers(config, api_key=os.environ.get("OPENAI_API_KEY"))


def inputs(case):
    config = configuration()
    site = config["sites"][case["site_id"]]
    source = (config["base"] / site["capture"]).resolve()
    if not source.is_relative_to(config["base"]) or file_digest(source) != case["source_hash"]:
        raise ConfigurationError("Frozen evaluation source hash/path mismatch")
    module, name = config["provider_factory"].split(":", 1)
    providers = getattr(importlib.import_module(module), name)(config["models"])
    identity = digest_json(
        {
            "source": case["source_hash"],
            "site": site,
            "embedding": asdict(providers.embedding),
            "models": config["models"],
        }
    )
    try:
        resources = ResourceScope(case["site_id"], config["base"] / config["resources"] / identity)
    except Exception:
        providers.close()
        raise
    return site, source, providers, resources


def prepare_cases(cases, sink):
    reports = []
    seen = set()
    for case in cases:
        key = case["site_id"], case["source_hash"]
        if key in seen:
            continue
        seen.add(key)
        site, source, providers, resources = inputs(case)
        with providers, build_runtime(site["config"], resources=resources, providers=providers) as runtime:
            if runtime.index_exists():
                runtime.ensure_index_loaded()
                continue
            state = resources.path("evaluation-input.json")
            if state.exists():
                run = json.loads(state.read_text())["run_id"]
            else:
                run = runtime.import_legacy(source, acknowledge_complete=True)
                atomic_json(state, {"run_id": run})
            context = OperationContext(
                operation_id="prepare-" + resources.root.name[:32], limits=OperationLimits.ingest(), sink=sink
            )
            result = runtime.run_ingest(mode="index_only", run_id=run, context=context, resume=True)
            if not result.get("indexed") or context.pending_events:
                raise ConfigurationError("Evaluation index setup did not complete")
            reports.append({"site_id": case["site_id"], "usage": context.summary()})
    return reports


def run_case(case, mode, context):
    site, _source, providers, resources = inputs(case)
    with (
        providers,
        build_runtime({**site["config"], "retrieval_mode": mode}, resources=resources, providers=providers) as runtime,
    ):
        if not runtime.index_exists():
            raise ConfigurationError("Prepare evaluation indexes before querying")
        result = runtime.query_result(case["question"], context=context)
        # Evaluation-only opt-in: artifacts contain website excerpts. Production
        # QueryResult diagnostics remain sanitized. This runner owns its runtime.
        result.trace["evaluation"] = {
            "supplied_text": [s["supplied_text"] for s in runtime.query_pipeline._last_used_sources],
        }
        return result


run_case.prepare = prepare_cases
