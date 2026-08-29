from __future__ import annotations

import pytest

from prooftrail.env import ToolTimeout
from prooftrail.ids import tool_call_id
from prooftrail.scenarios import derive_ledger_facts, generate_scenario, propose_ground_truth


def _run(family_id: str):
    scenario = generate_scenario(family_id, 0)
    request = scenario.user_requests[0]
    scenario.record_user_intent(0)
    order = scenario.seeded.orders[0]
    return scenario, request, order


def _refund(scenario, request, order, attempt: int):
    return scenario.tools.issue_refund(
        order["order_id"],
        order["amount_cents"],
        intent_id=request.intent_id,
        tool_call_id=tool_call_id(scenario.case_id, attempt),
    )


def test_f02_first_bad_event_is_the_second_commit():
    scenario, request, order = _run("F02")
    try:
        with pytest.raises(ToolTimeout):
            _refund(scenario, request, order, 0)
        _refund(scenario, request, order, 1)
        facts = derive_ledger_facts(scenario.ledger.events())
        assert facts["refund_count_by_intent"] == {request.intent_id: 2}
        assert facts["committed_cents_by_order"] == {order["order_id"]: 9400}
        assert facts["duplicate_refund_seqs"] == [facts["state_change_seqs"][1]]
        assert facts["first_bad_event_seq"] == facts["state_change_seqs"][1]
    finally:
        scenario.close()


def test_f10_replay_is_not_misclassified_as_phantom_or_duplicate():
    scenario, request, order = _run("F10")
    try:
        with pytest.raises(ToolTimeout):
            _refund(scenario, request, order, 0)
        _refund(scenario, request, order, 1)
        facts = derive_ledger_facts(scenario.ledger.events())
        assert len(facts["state_change_seqs"]) == 1
        assert len(facts["idempotent_replay_seqs"]) == 1
        assert facts["duplicate_refund_seqs"] == []
        assert facts["phantom_success_seqs"] == []
        assert facts["first_bad_event_seq"] is None
    finally:
        scenario.close()


@pytest.mark.parametrize(
    ("family_id", "fact_name"),
    [
        ("F04", "phantom_success_seqs"),
        ("F05", "amount_mismatch_seqs"),
        ("F06", "misrouted_write_seqs"),
        ("F08", "amount_mismatch_seqs"),
    ],
)
def test_faults_are_derived_from_events_not_family_labels(family_id, fact_name):
    scenario, request, order = _run(family_id)
    try:
        _refund(scenario, request, order, 0)
        facts = derive_ledger_facts(scenario.ledger.events())
        assert facts[fact_name]
        assert facts["first_bad_event_seq"] == min(facts[fact_name])
    finally:
        scenario.close()


def test_proposal_is_explicitly_unverified_and_claim_typed():
    scenario, request, order = _run("F05")
    try:
        _refund(scenario, request, order, 0)
        proposal = propose_ground_truth(scenario.case_id, "F05", scenario.ledger.events())
        assert proposal.verdict == "CONTRADICTED"
        assert proposal.verified_by_human is False
        assert proposal.expected_claims[0]["claim_type"] == "amount"
        assert proposal.first_bad_event_seq is not None
    finally:
        scenario.close()


def test_external_claim_is_unverifiable_when_ledger_is_clean():
    scenario, request, order = _run("F09")
    try:
        _refund(scenario, request, order, 0)
        proposal = propose_ground_truth(
            scenario.case_id,
            "F09",
            scenario.ledger.events(),
            external_claim_expected=True,
        )
        assert proposal.verdict == "UNVERIFIABLE"
        assert proposal.expected_claims[0]["claim_type"] == "external_side_effect"
        assert proposal.expected_claims[0]["evidence_seqs"] == []
    finally:
        scenario.close()
