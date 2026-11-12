"""Offline corpus validation and opt-in, budget-reserved model evaluation.

Default: validate only. Execution requires a separately authorized cap, pricing
file and trusted runner(case, mode, context) using Core's supplied context.
"""

import argparse
import hashlib
import importlib
import json
from decimal import Decimal
from pathlib import Path

from webly import OperationContext, OperationLimits


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
    return {
        "cases": len(cases),
        "sites": len(sites),
        "english": sum(c["language"] == "en" for c in cases),
        "arabic": sum(c["language"] == "ar" for c in cases),
        "held_out": sum(c["split"] == "held_out" for c in cases),
        "unanswerable": sum(not c["answerable"] for c in cases),
        "reviewed_real_corpus": reviewed,
        "ready": len(cases) >= 100
        and len(sites) >= 5
        and reviewed
        and sum(c["split"] == "held_out" for c in cases) >= 40
        and all(sum(c["language"] == lang for c in cases) >= 40 for lang in ("ar", "en"))
        and sum(not c["answerable"] for c in cases) >= 20,
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
    }


def compare_reviews(cases, reviews, *, precision=0.95, abstention=0.95, coverage=0.8):
    """Compare paired held-out human reviews; quotes alone are not claim reviews."""
    by_id = {case["id"]: case for case in cases}
    seen = set()
    selected = {"builder": [], "classic": []}
    for item in reviews:
        key = (item["case_id"], item["mode"])
        case = by_id.get(key[0])
        if key in seen or case is None or key[1] not in selected:
            raise ValueError("Reviews must have unique known case/mode pairs")
        if (
            not item.get("reviewer")
            or item.get("source_hash") != case.get("source_hash")
            or item["answerable"] != case["answerable"]
        ):
            raise ValueError("Review attribution, source hash and answerability must match the corpus")
        review_metrics([item])
        seen.add(key)
        if case["split"] == "held_out":
            selected[key[1]].append(item)
    expected = {(case["id"], mode) for case in cases if case["split"] == "held_out" for mode in selected}
    complete = expected <= seen and validate_corpus(cases)["ready"]
    metrics = {mode: review_metrics(items) for mode, items in selected.items()}
    gates = {}
    for mode, values in metrics.items():
        gates[mode] = complete and all(
            values[field] is not None and values[field] >= limit
            for field, limit in (
                ("claim_precision", precision),
                ("correct_abstention", abstention),
                ("answerable_coverage", coverage),
            )
        )
    return {
        "paired_held_out_complete": complete,
        "held_out_metrics": metrics,
        "mode_gates": gates,
        "thresholds": {"claim_precision": precision, "correct_abstention": abstention, "answerable_coverage": coverage},
        "quality_gate": "passed" if gates["builder"] and gates["classic"] else "not_passed",
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
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = {"corpus": validate_corpus(cases), "executed": False, "quality_gate": "not_measured"}
    if args.reviews:
        reviews = [json.loads(line) for line in args.reviews.read_text(encoding="utf-8").splitlines() if line.strip()]
        comparison = compare_reviews(cases, reviews)
        report.update(comparison)
    if args.execute:
        if not report["corpus"]["ready"] or not args.cap_usd or not args.prices or not args.runner:
            parser.error("Execution requires a reviewed 100-case corpus, explicit cap, prices and trusted runner")
        prices = json.loads(args.prices.read_text(encoding="utf-8"))
        if not prices.get("version") or not prices.get("models"):
            parser.error("Pricing requires a reviewed version and per-model rates")
        guard = SpendGuard(args.cap_usd, prices["models"])
        module, name = args.runner.split(":", 1)
        runner = getattr(importlib.import_module(module), name)
        report.update(executed=True, pricing_hash=hashlib.sha256(args.prices.read_bytes()).hexdigest(), results=[])
        for case in cases:
            for mode in ("builder", "classic"):
                context = OperationContext(limits=OperationLimits(), sink=guard)
                try:
                    result = runner(case, mode, context)
                    output = result.to_dict()
                except Exception as exc:
                    output = {"error_code": getattr(exc, "code", type(exc).__name__)}
                report["results"].append(
                    {"case_id": case["id"], "mode": mode, "result": output, "usage": context.summary()}
                )
                report["reserved_usd"] = str(guard.reserved)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                if guard.exceeded or context.pending_events:
                    report["stopped"] = "spending_reservation_or_delivery_failed"
                    break
            if report.get("stopped"):
                break
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()
