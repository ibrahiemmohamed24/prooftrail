"""Deterministic metrics shared by every auditor.

The headline accuracy is an unweighted mean over scenario families.  That is
intentional: generating more superficial variants of one family must not make
an auditor look better than it is.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import fmean
from typing import Iterable, Mapping

from ..schemas.verdict import AuditOutput, GroundTruth, STATUSES


def macro_f1(actual: Iterable[str], predicted: Iterable[str]) -> float:
    """Return macro-F1 over the three public verdict classes.

    Classes absent from both truth and predictions are omitted.  This keeps a
    small smoke run (for example, only the killer case) interpretable while a
    complete evaluation naturally includes every represented class.
    """

    y_true = list(actual)
    y_pred = list(predicted)
    if len(y_true) != len(y_pred):
        raise ValueError("actual and predicted must have the same length")
    if not y_true:
        return 0.0

    scores: list[float] = []
    for label in STATUSES:
        support = sum(value == label for value in y_true)
        predicted_count = sum(value == label for value in y_pred)
        if support == 0 and predicted_count == 0:
            continue
        true_positive = sum(
            truth == label and guess == label
            for truth, guess in zip(y_true, y_pred, strict=True)
        )
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else 0.0
        scores.append(
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
    return fmean(scores) if scores else 0.0


def evaluate_outputs(
    outputs: Mapping[str, AuditOutput],
    truths: Mapping[str, GroundTruth],
    *,
    include_unverified: bool = False,
) -> dict[str, object]:
    """Score auditor outputs against hidden labels.

    By default only human-verified cases count.  ``include_unverified`` exists
    for development smoke runs and is always surfaced in the returned report,
    so provisional numbers cannot be mistaken for the headline result.
    """

    missing = sorted(set(outputs) - set(truths))
    if missing:
        raise KeyError(f"missing ground truth for: {', '.join(missing)}")

    case_ids = [
        case_id
        for case_id in sorted(outputs)
        if include_unverified or truths[case_id].verified_by_human
    ]
    family_hits: dict[str, list[bool]] = defaultdict(list)
    actual: list[str] = []
    predicted: list[str] = []
    first_bad_total = 0
    first_bad_hits = 0
    cited_claims = 0
    total_claims = 0

    for case_id in case_ids:
        output = outputs[case_id]
        truth = truths[case_id]
        actual.append(truth.verdict)
        predicted.append(output.verdict)
        family_hits[truth.family_id].append(output.verdict == truth.verdict)

        if truth.first_bad_event_seq is not None:
            first_bad_total += 1
            first_bad_hits += output.first_bad_event_seq == truth.first_bad_event_seq

        cited, total = output.evidence_coverage
        cited_claims += cited
        total_claims += total

    per_family = {
        family_id: {
            "accuracy": sum(hits) / len(hits),
            "correct": sum(hits),
            "total": len(hits),
        }
        for family_id, hits in sorted(family_hits.items())
    }
    family_accuracies = [row["accuracy"] for row in per_family.values()]

    return {
        "case_count": len(case_ids),
        "verified_only": not include_unverified,
        "overall_accuracy": (
            sum(truth == guess for truth, guess in zip(actual, predicted, strict=True))
            / len(case_ids)
            if case_ids
            else 0.0
        ),
        "family_mean_accuracy": fmean(family_accuracies) if family_accuracies else 0.0,
        "macro_f1": macro_f1(actual, predicted),
        "first_bad_event": {
            "hit_rate": first_bad_hits / first_bad_total if first_bad_total else 0.0,
            "hits": first_bad_hits,
            "eligible": first_bad_total,
        },
        "evidence_coverage": {
            "rate": cited_claims / total_claims if total_claims else 0.0,
            "cited": cited_claims,
            "total": total_claims,
        },
        "per_family": per_family,
    }
