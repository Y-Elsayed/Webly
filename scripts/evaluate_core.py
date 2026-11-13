"""Offline corpus validation and opt-in, budget-reserved model evaluation.

Default: validate only. Execution requires a separately authorized cap, pricing
file and trusted runner(case, mode, context) using Core's supplied context.
"""

import argparse
import hashlib
import importlib
import json
import uuid
from decimal import Decimal
from pathlib import Path

from webly import OperationContext, OperationLimits
from webly.contracts import atomic_json, digest_json


class SpendGuard:
    def __init__(self, cap, prices):
        self.cap = Decimal(str(cap))
        self.prices = prices
        self.reserved = Decimal("0")
        self.exceeded = False
        if not self.cap.is_finite() or self.cap <= 0:
            raise ValueError("A positive finite spending cap is required")
        for rates in prices.values():
            for key in ("input_per_million", "output_per_million"):
                rate = Decimal(str(rates[key]))
                if not rate.is_finite() or rate < 0:
                    raise ValueError("Rates must be finite nonnegative USD amounts")

    def __call__(self, event):
        if event["kind"] != "provider_started":
            return
        rates = self.prices.get(event["model"])
        if rates is None:
            self.exceeded = True
            raise ValueError("Pricing missing for a model; refusing paid work")
        amount = (
            Decimal(event["input_tokens"]) * Decimal(str(rates["input_per_million"]))
            + Decimal(event["output_tokens"]) * Decimal(str(rates["output_per_million"]))
        ) / Decimal(1_000_000)
        if self.reserved + amount > self.cap:
            self.exceeded = True
            raise ValueError("Evaluation spending cap would be exceeded")
        self.reserved += amount  # conservative: unknown/retried calls are never refunded


def validate_corpus(cases):
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs")
    for case in cases:
        if case.get("language") not in {"en", "ar"} or case.get("split") not in {"development", "held_out"}:
            raise ValueError("Each case needs a language and explicit evaluation split")
        if not case.get("question") or not case.get("site_id") or not isinstance(case.get("answerable"), bool):
            raise ValueError("Question, site and answerability are required")
        if case.get("reviewed") and (not case.get("reviewer") or not case.get("source_hash")):
            raise ValueError("Reviewed cases require reviewer attribution and source hash")
        if case.get("reviewed") and case["answerable"] and not case.get("supporting_spans"):
            raise ValueError("Reviewed answerable cases require approved evidence")
    sites = {case["site_id"] for case in cases}
    reviewed = all(case.get("reviewed") is True and not case.get("synthetic", False) for case in cases)
    reviewed = reviewed and not any(c.get("requires_rewrite") or c.get("draft_question") for c in cases)
    questions = [(c["site_id"], c["language"], " ".join(c["question"].split()).casefold()) for c in cases]
    duplicates = len(questions) - len(set(questions))
    return {
        "cases": len(cases),
        "sites": len(sites),
        "english": sum(c["language"] == "en" for c in cases),
        "arabic": sum(c["language"] == "ar" for c in cases),
        "held_out": sum(c["split"] == "held_out" for c in cases),
        "unanswerable": sum(not c["answerable"] for c in cases),
        "reviewed_real_corpus": reviewed,
        "duplicate_questions": duplicates,
        "ready": len(cases) >= 100
        and len(sites) >= 5
        and reviewed
        and not duplicates
        and sum(c["split"] == "held_out" for c in cases) >= 40
        and all(sum(c["language"] == lang for c in cases) >= 40 for lang in ("ar", "en"))
        and sum(not c["answerable"] for c in cases) >= 20
        and all(
            sum(c["split"] == "held_out" and not c["answerable"] and c["language"] == lang for c in cases) >= 5
            for lang in ("en", "ar")
        )
        and all(
            sum(c["split"] == "held_out" and c["site_id"] == site and c["language"] == lang for c in cases) >= 2
            for site in sites
            for lang in ("en", "ar")
        ),
    }


def review_metrics(reviews):
    for item in reviews:
        for field in ("total_claims", "supported_claims"):
            if type(item[field]) is not int or item[field] < 0:
                raise ValueError("Claim counts must be nonnegative integers")
        if item["supported_claims"] > item["total_claims"]:
            raise ValueError("Supported claims cannot exceed total claims")
        if any(type(item[field]) is not bool for field in ("answerable", "correct_abstention", "answered")):
            raise ValueError("Review outcomes must be explicit booleans")
        if "total_citations" in item or "correct_citations" in item:
            if any(
                type(item.get(field)) is not int or item[field] < 0
                for field in ("total_citations", "correct_citations")
            ):
                raise ValueError("Citation counts must be nonnegative integers")
            if item["correct_citations"] > item["total_citations"]:
                raise ValueError("Correct citations cannot exceed total citations")
    claims = sum(item["total_claims"] for item in reviews)
    supported = sum(item["supported_claims"] for item in reviews)
    absent = [item for item in reviews if not item["answerable"]]
    return {
        "reviewed_answers": len(reviews),
        "claim_precision": supported / claims if claims else None,
        "correct_abstention": sum(item["correct_abstention"] for item in absent) / len(absent) if absent else None,
        "answer_coverage": sum(item["answered"] for item in reviews) / len(reviews) if reviews else None,
        "answerable_coverage": (
            sum(item["answered"] and item["answerable"] for item in reviews)
            / sum(item["answerable"] for item in reviews)
            if any(item["answerable"] for item in reviews)
            else None
        ),
        "citation_accuracy": (
            sum(r.get("correct_citations", 0) for r in reviews) / sum(r.get("total_citations", 0) for r in reviews)
            if sum(r.get("total_citations", 0) for r in reviews)
            else None
        ),
    }


def compare_reviews(cases, reviews, *, results=None, precision=0.95, abstention=0.95, coverage=0.8):
    """Compare paired held-out human reviews; quotes alone are not claim reviews."""
    by_id = {case["id"]: case for case in cases}
    seen = set()
    selected = {"builder": [], "classic": []}
    if not results or not results.get("run_id") or not results.get("executed"):
        raise ValueError("Quality reviews require the corresponding executed results report")
    if results.get("corpus_hash") != digest_json(cases):
        raise ValueError("The evaluated corpus changed; rerun before reviewing")
    responses = {(r["case_id"], r["mode"]): r for r in results["results"]}
    if len(responses) != len(results["results"]):
        raise ValueError("Duplicate result identities")
    for item in reviews:
        key = (item["case_id"], item["mode"])
        case = by_id.get(key[0])
        response = responses.get(key)
        if (
            case is None
            or response is None
            or item.get("run_id") != results["run_id"]
            or item.get("response_hash") != digest_json(response["result"])
            or response.get("source_hash") != case.get("source_hash")
        ):
            raise ValueError("Review does not match the exact run, source and response")
        if key in seen or case is None or key[1] not in selected:
            raise ValueError("Reviews must have unique known case/mode pairs")
        if (
            not item.get("reviewer")
            or item.get("source_hash") != case.get("source_hash")
            or item["answerable"] != case["answerable"]
        ):
            raise ValueError("Review attribution, source hash and answerability must match the corpus")
        review_metrics([item])
        if "total_citations" not in item or "correct_citations" not in item:
            raise ValueError("Quality reviews require explicit citation counts")
        seen.add(key)
        if case["split"] == "held_out":
            selected[key[1]].append(item)
    expected = {(case["id"], mode) for case in cases if case["split"] == "held_out" for mode in selected}
    complete = expected <= seen and validate_corpus(cases)["ready"]
    metrics = {mode: review_metrics(items) for mode, items in selected.items()}
    languages = {
        lang: {
            mode: review_metrics([r for r in rows if by_id[r["case_id"]]["language"] == lang])
            for mode, rows in selected.items()
        }
        for lang in ("en", "ar")
    }
    gates = {}
    for mode, values in metrics.items():
        gates[mode] = complete and all(
            language[mode][field] is not None and language[mode][field] >= limit
            for language in languages.values()
            for field, limit in (
                ("claim_precision", precision),
                ("correct_abstention", abstention),
                ("answerable_coverage", coverage),
                ("citation_accuracy", precision),
            )
        )
    return {
        "paired_held_out_complete": complete,
        "held_out_metrics": metrics,
        "mode_gates": gates,
        "thresholds": {
            "claim_precision": precision,
            "correct_abstention": abstention,
            "answerable_coverage": coverage,
            "citation_accuracy": precision,
        },
        "quality_gate": "passed" if gates["builder"] and gates["classic"] else "not_passed",
        "by_language": languages,
        "by_site": {
            site: {
                mode: review_metrics([r for r in rows if by_id[r["case_id"]]["site_id"] == site])
                for mode, rows in selected.items()
            }
            for site in sorted({c["site_id"] for c in cases})
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cap-usd")
    parser.add_argument("--prices", type=Path)
    parser.add_argument("--runner", help="Trusted module:function taking case, mode, context")
    parser.add_argument("--output", type=Path, default=Path("evaluation-results.json"))
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--results", type=Path, help="Executed report whose exact responses were reviewed")
    args = parser.parse_args()
    if args.execute and (args.reviews or args.results):
        parser.error("Execute and review are separate steps; reviews must bind to a completed run")
    cases = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = {"corpus": validate_corpus(cases), "executed": False, "quality_gate": "not_measured"}
    if args.reviews:
        reviews = [json.loads(line) for line in args.reviews.read_text(encoding="utf-8").splitlines() if line.strip()]
        previous = json.loads(args.results.read_text(encoding="utf-8")) if args.results else None
        comparison = compare_reviews(cases, reviews, results=previous)
        if previous:
            report.update(previous)
            report["corpus"] = validate_corpus(cases)
        report.update(comparison)
        report["reviewed_execution_metrics"] = execution_metrics(report.get("results", []), reviews)
    if args.execute:
        if not report["corpus"]["ready"] or not args.cap_usd or not args.prices or not args.runner:
            parser.error("Execution requires a reviewed 100-case corpus, explicit cap, prices and trusted runner")
        prices = json.loads(args.prices.read_text(encoding="utf-8"))
        if not prices.get("version") or not prices.get("models"):
            parser.error("Pricing requires a reviewed version and per-model rates")
        guard = SpendGuard(args.cap_usd, prices["models"])
        module, name = args.runner.split(":", 1)
        runner = getattr(importlib.import_module(module), name)
        report.update(
            executed=True,
            run_id=uuid.uuid4().hex,
            corpus_hash=digest_json(cases),
            pricing_hash=hashlib.sha256(args.prices.read_bytes()).hexdigest(),
            results=[],
        )
        prepare = getattr(runner, "prepare", None)
        if prepare:
            try:
                report["setup"] = prepare(cases, guard)
            except Exception as exc:
                report["stopped"] = "setup_failed"
                report["setup_error_code"] = getattr(exc, "code", type(exc).__name__)
        for case in cases:
            if report.get("stopped"):
                break
            for mode in ("builder", "classic"):
                context = OperationContext(limits=OperationLimits(), sink=guard)
                before_cost = guard.reserved
                try:
                    result = runner(case, mode, context)
                    output = result.to_dict()
                except Exception as exc:
                    output = {"error_code": getattr(exc, "code", type(exc).__name__)}
                report["results"].append(
                    {
                        "case_id": case["id"],
                        "mode": mode,
                        "source_hash": case["source_hash"],
                        "language": case["language"],
                        "site_id": case["site_id"],
                        "result": output,
                        "response_hash": digest_json(output),
                        "usage": context.summary(),
                        "reserved_usd": str(guard.reserved - before_cost),
                        "retrieval_evidence_recall": evidence_recall(case, output),
                    }
                )
                report["reserved_usd"] = str(guard.reserved)
                atomic_json(args.output, report)
                if guard.exceeded or context.pending_events:
                    report["stopped"] = "spending_reservation_or_delivery_failed"
                    break
            if report.get("stopped"):
                break
    report["execution_metrics"] = execution_metrics(report.get("results", []))
    report["execution_by_language"] = {
        lang: execution_metrics([r for r in report.get("results", []) if r.get("language") == lang])
        for lang in ("en", "ar")
    }
    atomic_json(args.output, report)
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))


def execution_metrics(rows, reviews=None):
    import statistics

    output = {}
    for mode in ("builder", "classic"):
        selected = [r for r in rows if r["mode"] == mode]
        times = sorted(r["usage"]["elapsed_s"] for r in selected)
        recall = [r["retrieval_evidence_recall"] for r in selected if r.get("retrieval_evidence_recall") is not None]
        successful = sum(
            r["answered"]
            and r["total_claims"] > 0
            and r["supported_claims"] == r["total_claims"]
            and r.get("total_citations", 0) > 0
            and r.get("correct_citations") == r.get("total_citations")
            for r in (reviews or [])
            if r["mode"] == mode
        )
        cost = sum((Decimal(r["reserved_usd"]) for r in selected), Decimal(0))
        output[mode] = {
            "attempted": len(selected),
            "errors": sum("error_code" in r["result"] for r in selected),
            "p50_s": statistics.median(times) if times else None,
            "p95_s": times[min(len(times) - 1, int(len(times) * 0.95))] if times else None,
            "reserved_usd": str(cost),
            "mean_evidence_recall": statistics.mean(recall) if recall else None,
            "cost_per_human_verified_success": str(cost / successful) if successful else None,
        }
    return output


def evidence_recall(case, output):
    expected = case.get("supporting_spans", [])
    supplied = output.get("trace", {}).get("evaluation", {}).get("supplied_text", [])
    if not expected:
        return None
    if not supplied:
        return 0.0
    spans = [s if isinstance(s, str) else s["text"] for s in expected]
    return sum(any(span in text for text in supplied) for span in spans) / len(spans)


if __name__ == "__main__":
    main()
