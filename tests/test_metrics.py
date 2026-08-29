from prooftrail.eval.metrics import evaluate_outputs, macro_f1
from prooftrail.schemas.verdict import (
    AuditOutput,
    ClaimType,
    ClaimVerdict,
    GroundTruth,
    Status,
)


def _truth(case_id, family_id, verdict, first_bad=None, verified=True):
    return GroundTruth(
        case_id=case_id,
        family_id=family_id,
        verdict=verdict,
        first_bad_event_seq=first_bad,
        expected_claims=[],
        ledger_facts={},
        verified_by_human=verified,
    )


def _output(case_id, verdict, first_bad=None, cited=True):
    return AuditOutput(
        case_id=case_id,
        auditor="prooftrail",
        verdict=verdict,
        claims=[
            ClaimVerdict(
                claim_id="c1",
                claim_text="I refunded $47.00",
                claim_type=ClaimType.REFUND_ISSUED,
                status=verdict,
                evidence_seqs=[3] if cited else [],
            )
        ],
        first_bad_event_seq=first_bad,
    )


def test_macro_f1_perfect_and_length_guard():
    labels = [Status.SUPPORTED, Status.CONTRADICTED, Status.UNVERIFIABLE]
    assert macro_f1(labels, labels) == 1.0
    try:
        macro_f1(labels, labels[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched lengths must fail")


def test_evaluate_outputs_family_weighting_and_first_bad():
    truths = {
        "a": _truth("a", "F01", Status.SUPPORTED),
        "b": _truth("b", "F01", Status.SUPPORTED),
        "c": _truth("c", "F02", Status.CONTRADICTED, first_bad=7),
    }
    outputs = {
        "a": _output("a", Status.SUPPORTED),
        "b": _output("b", Status.CONTRADICTED, cited=False),
        "c": _output("c", Status.CONTRADICTED, first_bad=7),
    }
    report = evaluate_outputs(outputs, truths)
    assert report["overall_accuracy"] == 2 / 3
    assert report["family_mean_accuracy"] == 0.75
    assert report["first_bad_event"] == {"hit_rate": 1.0, "hits": 1, "eligible": 1}
    assert report["evidence_coverage"] == {"rate": 2 / 3, "cited": 2, "total": 3}


def test_unverified_cases_are_excluded_by_default():
    truths = {"a": _truth("a", "F01", Status.SUPPORTED, verified=False)}
    outputs = {"a": _output("a", Status.SUPPORTED)}
    assert evaluate_outputs(outputs, truths)["case_count"] == 0
    assert evaluate_outputs(outputs, truths, include_unverified=True)["case_count"] == 1
