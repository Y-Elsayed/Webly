from decimal import Decimal

import pytest

from scripts.evaluate_core import SpendGuard, compare_reviews, review_metrics, validate_corpus


def test_budget_reserves_before_work_and_does_not_refund_unknown_calls():
    guard = SpendGuard("0.001", {"model": {"input_per_million": "1", "output_per_million": "2"}})
    event = {"kind": "provider_started", "model": "model", "input_tokens": 500, "output_tokens": 100}
    guard(event)
    assert guard.reserved == Decimal("0.0007")
    with pytest.raises(ValueError):
        guard(event)
    assert guard.reserved <= guard.cap and guard.exceeded


def test_missing_prices_and_invalid_caps_fail_closed():
    for cap in ("0", "-1", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            SpendGuard(cap, {})
    guard = SpendGuard("1", {})
    with pytest.raises(ValueError):
        guard({"kind": "provider_started", "model": "unknown"})


def test_synthetic_or_unreviewed_questions_cannot_pass_real_quality_gate():
    cases = [
        {
            "id": str(i),
            "site_id": str(i % 5),
            "language": "ar" if i % 2 else "en",
            "split": "held_out" if i < 40 else "development",
            "question": "Question?",
            "answerable": i >= 20,
            "reviewed": False,
        }
        for i in range(100)
    ]
    assert not validate_corpus(cases)["ready"]
    for case in cases:
        case.update(reviewed=True, reviewer="fixture-reviewer", source_hash="fixture-hash", supporting_spans=["fact"])
    assert validate_corpus(cases)["ready"]
    cases[0]["synthetic"] = True
    assert not validate_corpus(cases)["ready"]


def test_empty_or_all_abstained_answers_do_not_manufacture_claim_precision():
    metrics = review_metrics(
        [{"total_claims": 0, "supported_claims": 0, "answerable": False, "correct_abstention": True, "answered": False}]
    )
    assert metrics["claim_precision"] is None
    assert metrics["answer_coverage"] == 0


def test_reviews_reject_impossible_counts_and_unmatched_source():
    item = {
        "case_id": "one",
        "mode": "builder",
        "reviewer": "person",
        "source_hash": "hash",
        "total_claims": 1,
        "supported_claims": 2,
        "answerable": True,
        "correct_abstention": False,
        "answered": True,
    }
    with pytest.raises(ValueError):
        review_metrics([item])
    item["supported_claims"] = 1
    cases = [{"id": "one", "source_hash": "changed", "answerable": True}]
    with pytest.raises(ValueError):
        compare_reviews(cases, [item])
