"""Freeze five public HTML captures and draft bilingual cases, never human approvals.

Network requests use Core's crawler/robots/fetch boundary. No model calls occur.
Outputs include full HTML and stay in ignored evaluation_artifacts by default.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts.worker_example import fixture_providers
from webly import OperationContext, OperationLimits, ResourceScope, build_runtime
from webly.contracts import atomic_json
from webly.crawl.runs import file_digest
from webly.processors.text_chunkers import SlidingTextChunker


def draft_cases(site_id, path):
    candidates = []
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        page = json.loads(line)
        for chunk in SlidingTextChunker().chunk_html(page["html"], page["url"]):
            for block in chunk["blocks"]:
                if block["kind"] not in {"p", "li", "text", "blockquote"}:
                    continue
                words = list(re.finditer(r"\S+", block["text"]))
                if len(words) < 8 or block["text"] in seen:
                    continue
                span = block["text"][: words[7].end()]
                seen.add(block["text"])
                candidates.append(
                    {
                        "text": span,
                        "url": page["url"],
                        "block_id": block["block_id"],
                        "topic": " ".join(chunk.get("hierarchy", [])[-1:]).split()[:3],
                    }
                )
    if len(candidates) < 8:
        raise ValueError("Capture needs at least eight distinct reviewable factual blocks")
    source_hash = file_digest(path)
    cases = []
    for index, evidence in enumerate(candidates[:8]):
        topic = " ".join(evidence.pop("topic")) or site_id
        for language in ("en", "ar"):
            question = (
                f"What information does the section ‘{topic}’ provide?"
                if language == "en"
                else f"ما المعلومات التي يقدمها القسم «{topic}»؟"
            )
            cases.append(
                {
                    "id": f"{site_id}-{index}-{language}",
                    "site_id": site_id,
                    "language": language,
                    "split": "development" if index < 6 else "held_out",
                    "question": question,
                    "answerable": True,
                    "source_hash": source_hash,
                    "supporting_spans": [evidence],
                    "reviewed": False,
                    "reviewer": None,
                    "synthetic": False,
                    "draft_question": True,
                    "requires_rewrite": True,
                }
            )
    unknown = {
        "en": [
            "What is the unpublished staff-only access code?",
            "What is the organization's undocumented internal identifier?",
        ],
        "ar": ["ما رمز الدخول غير المنشور المخصص للموظفين؟", "ما المعرّف الداخلي غير الموثق للمؤسسة؟"],
    }
    for language, questions in unknown.items():
        for index, question in enumerate(questions):
            cases.append(
                {
                    "id": f"{site_id}-missing-{index}-{language}",
                    "site_id": site_id,
                    "language": language,
                    "split": "held_out",
                    "question": question,
                    "answerable": False,
                    "source_hash": source_hash,
                    "supporting_spans": [],
                    "reviewed": False,
                    "reviewer": None,
                    "synthetic": False,
                    "draft_question": True,
                    "requires_rewrite": True,
                }
            )
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("docs/evaluation/sources.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation_artifacts"))
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    config = {
        "provider_factory": "scripts.evaluation_runner:openai_providers",
        "resources": "resources",
        "models": {"embedding_model": "SELECT_BEFORE_LIVE_RUN", "chat_model": "SELECT_BEFORE_LIVE_RUN"},
        "sites": {},
    }
    cases, failures, captured = [], [], []
    for site in json.loads(args.sources.read_text(encoding="utf-8"))["sources"]:
        project = {
            "start_url": site["url"],
            "crawl_entire_site": False,
            "max_depth": 0,
            "respect_robots": True,
            "retrieval_mode": "classic",
        }
        providers = fixture_providers()
        try:
            with (
                providers,
                build_runtime(
                    project,
                    resources=ResourceScope(site["site_id"], root / "captures" / site["site_id"]),
                    providers=providers,
                ) as runtime,
            ):
                state = root / (site["site_id"] + "-capture.json")
                if state.exists():
                    run = json.loads(state.read_text())["run_id"]
                    if not runtime.inspect_run(run)["compatibility"]["compatible"]:
                        raise ValueError("Saved capture policy changed; remove only this draft state and recrawl")
                else:
                    result = runtime.run_ingest(
                        mode="crawl_only",
                        context=OperationContext(
                            limits=OperationLimits.ingest(timeout_s=120, total_bytes=20 * 1024 * 1024)
                        ),
                    )
                    run = result["run_id"]
                    atomic_json(state, {"run_id": run})
                source = runtime.resources.path("runs", run, "results.jsonl")
                cases.extend(draft_cases(site["site_id"], source))
                config["sites"][site["site_id"]] = {"capture": source.relative_to(root).as_posix(), "config": project}
                captured.append({**site, "source_hash": file_digest(source), "run_id": run})
        except Exception as exc:
            failures.append({"site_id": site["site_id"], "error_code": getattr(exc, "code", type(exc).__name__)})
    (root / "corpus.draft.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8"
    )
    atomic_json(root / "runner-config.json", config)
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "real_model_calls": False,
        "human_reviewed": False,
        "quality_ready": False,
        "draft_cases": len(cases),
        "captures": captured,
        "failures": failures,
    }
    atomic_json(root / "preparation.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
