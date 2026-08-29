import json

import pytest

from prooftrail.schemas import (
    AgentTrace,
    AuditOutput,
    ClaimVerdict,
    EventType,
    FrozenCase,
    GroundTruth,
    LedgerEvent,
    ToolCallRecord,
    Usage,
    aggregate_verdict,
    validate_audit_output,
)


def test_aggregate_verdict_precedence():
    assert aggregate_verdict([]) == "UNVERIFIABLE"
    assert aggregate_verdict(["SUPPORTED", "SUPPORTED"]) == "SUPPORTED"
    assert aggregate_verdict(["SUPPORTED", "UNVERIFIABLE"]) == "UNVERIFIABLE"
    assert aggregate_verdict(["UNVERIFIABLE", "CONTRADICTED", "SUPPORTED"]) == "CONTRADICTED"


def test_claim_and_output_validation_in_constructors():
    with pytest.raises(ValueError):
        ClaimVerdict("c1", "x", "refund_issued", "MAYBE")
    with pytest.raises(ValueError):
        ClaimVerdict("c1", "x", "vibes", "SUPPORTED")
    with pytest.raises(ValueError):
        AuditOutput("case", "B1", "MAYBE", [], None)


def test_evidence_coverage_and_roundtrip():
    out = AuditOutput(
        case_id="F02-s00",
        auditor="prooftrail",
        verdict="CONTRADICTED",
        claims=[
            ClaimVerdict("c1", "I refunded $84.00", "refund_issued", "CONTRADICTED", [4, 9], "two commits"),
            ClaimVerdict("c2", "sent an email", "external_side_effect", "UNVERIFIABLE"),
        ],
        first_bad_event_seq=9,
        usage={"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0002, "llm_calls": 1},
    )
    assert out.evidence_coverage == (1, 2)
    d = out.to_dict()
    assert d["evidence_coverage"] == {"cited": 1, "total": 2}
    back = AuditOutput.from_dict(json.loads(json.dumps(d)))
    assert back == out


def test_validate_audit_output_catches_llm_garbage():
    assert validate_audit_output("not a dict") == ["output is not an object"]
    bad = {
        "verdict": "TRUE",
        "first_bad_event_seq": "9",
        "claims": [
            {"claim_text": "", "claim_type": "refund_issued", "status": "SUPPORTED", "evidence_seqs": [1, "2"]},
            "nope",
        ],
    }
    problems = validate_audit_output(bad)
    assert any("verdict" in p for p in problems)
    assert any("first_bad_event_seq" in p for p in problems)
    assert any("claim_text" in p for p in problems)
    assert any("evidence_seqs" in p for p in problems)
    assert any("claims[1]" in p for p in problems)
    assert validate_audit_output({"verdict": "SUPPORTED", "claims": []}) == []
    assert validate_audit_output({"verdict": "SUPPORTED", "claims": [], "first_bad_event_seq": True})


def test_frozen_case_roundtrip():
    ev = LedgerEvent(seq=1, ts="2026-08-28T09:00:07+00:00", event_type=EventType.USER_INTENT,
                     intent_id="int_1", payload={"text": "refund"}).seal("0" * 64)
    trace = AgentTrace(
        case_id="F01-s00",
        model="claude-opus-5",
        system_prompt_sha256="abc",
        user_requests=[{"intent_id": "int_1", "text": "refund"}],
        messages=[{"role": "user", "content": "refund"}],
        tool_calls=[ToolCallRecord("tc_1", "int_1", "lookup_order", {"order_id": "ord_1"}, {"status": "paid"}, None, 2, 3)],
        final_report="Refunded.",
        usage=Usage(100, 20, 0.001, 2),
        stop_reason="end_turn",
    )
    case = FrozenCase("F01-s00", "F01", 0, trace, [ev])
    back = FrozenCase.from_dict(json.loads(json.dumps(case.to_dict())))
    assert back == case
    assert back.ledger[0].hash == ev.hash


def test_ground_truth_roundtrip_and_default_unverified():
    gt = GroundTruth("F02-s00", "F02", "CONTRADICTED", 9, [{"claim_type": "count", "status": "CONTRADICTED"}],
                     {"refund_count": 2})
    assert gt.verified_by_human is False
    assert GroundTruth.from_dict(gt.to_dict()) == gt


def test_usage_add():
    assert Usage(1, 2, 0.5, 1).add(Usage(3, 4, 0.25, 1)) == Usage(4, 6, 0.75, 2)
