from prooftrail.baselines.b1_trace_plus_ledger import B1Auditor, InvalidBaselineOutput
from prooftrail.schemas.events import EventType, LedgerEvent
from prooftrail.schemas.trace import AgentTrace, FrozenCase, Usage
from prooftrail.schemas.verdict import ClaimType, Status


def _case():
    event = LedgerEvent(
        seq=1,
        ts="2026-08-28T09:00:07+00:00",
        event_type=EventType.STATE_CHANGED,
        state_after={"refunded_cents": 4700},
    ).seal("0" * 64)
    trace = AgentTrace(
        case_id="F02-s00",
        model="scripted-offline",
        system_prompt_sha256="abc",
        user_requests=[],
        messages=[],
        tool_calls=[],
        final_report="I refunded $47.00 for order ord_1.",
    )
    return FrozenCase("F02-s00", "F02", 0, trace, [event])


class FakeClient:
    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.raw, Usage(input_tokens=100, output_tokens=20, llm_calls=1)


def test_b1_gets_trace_and_ledger_in_exactly_one_call():
    raw = {
        "verdict": Status.SUPPORTED,
        "claims": [{
            "claim_id": "c1",
            "claim_text": "I refunded $47.00 for order ord_1.",
            "claim_type": ClaimType.REFUND_ISSUED,
            "status": Status.SUPPORTED,
            "evidence_seqs": [1],
            "reason": "matched",
        }],
        "first_bad_event_seq": None,
        "explanation": "matched ledger",
    }
    client = FakeClient(raw)
    result = B1Auditor(client, model="gemini-3.1-flash-lite").audit(_case())
    assert result.verdict == Status.SUPPORTED
    assert result.usage["llm_calls"] == 1
    assert len(client.calls) == 1
    prompt = client.calls[0]["user_prompt"]
    assert "final_report" in prompt
    assert "state_after" in prompt
    assert "refunded_cents" in prompt
    assert "family_id" not in prompt
    assert "F02-s00" not in prompt


def test_b1_rejects_malformed_output_instead_of_repairing_it():
    client = FakeClient({"verdict": "MAYBE", "claims": []})
    try:
        B1Auditor(client, model="gemini-3.1-flash-lite").audit(_case())
    except InvalidBaselineOutput:
        pass
    else:
        raise AssertionError("malformed model output must fail closed")
