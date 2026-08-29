"""Deterministic facts and provisional labels derived only from the ledger.

The proposal returned here is intentionally ``verified_by_human=False``.  A
later freezing step can add claim-aware labels and approve them; auditors must
never import or call this module.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from ..schemas.events import EventType, LedgerEvent, verify_chain
from ..schemas.verdict import ClaimType, GroundTruth, Status, aggregate_verdict


def derive_ledger_facts(events: Iterable[LedgerEvent]) -> dict[str, Any]:
    ordered = list(events)
    chain_valid, first_chain_error = verify_chain(ordered)
    commits = [event for event in ordered if event.event_type == EventType.STATE_CHANGED]
    replays = [event for event in ordered if event.event_type == EventType.IDEMPOTENT_REPLAY]

    commits_by_intent: dict[str, list[LedgerEvent]] = defaultdict(list)
    committed_cents_by_order: dict[str, int] = {}
    for event in commits:
        commits_by_intent[event.intent_id or "<missing>"].append(event)
        if event.entity and event.state_after is not None:
            committed_cents_by_order[event.entity.removeprefix("order:")] = int(
                event.state_after.get("refunded_cents", 0)
            )

    duplicate_refund_seqs = [
        event.seq
        for same_intent in commits_by_intent.values()
        for event in same_intent[1:]
    ]
    misrouted_write_seqs: list[int] = []
    amount_mismatch_seqs: list[int] = []
    for event in commits:
        requested_order = event.payload.get("requested_order_id")
        if requested_order and event.entity != f"order:{requested_order}":
            misrouted_write_seqs.append(event.seq)
        requested_amount = event.payload.get("requested_amount_cents")
        if requested_amount is not None and event.state_before is not None and event.state_after is not None:
            actual_delta = int(event.state_after.get("refunded_cents", 0)) - int(
                event.state_before.get("refunded_cents", 0)
            )
            if actual_delta != requested_amount:
                amount_mismatch_seqs.append(event.seq)

    commit_call_ids = {event.tool_call_id for event in commits}
    replay_call_ids = {event.tool_call_id for event in replays}
    phantom_success_seqs = [
        event.seq
        for event in ordered
        if event.event_type == EventType.TOOL_CALL_COMPLETED
        and event.tool_name == "issue_refund"
        and event.payload.get("ok") is True
        and event.tool_call_id not in commit_call_ids
        and event.tool_call_id not in replay_call_ids
    ]

    anomaly_seqs = sorted(
        set(duplicate_refund_seqs + misrouted_write_seqs + amount_mismatch_seqs + phantom_success_seqs)
    )
    return {
        "chain_valid": chain_valid,
        "first_chain_error_seq": first_chain_error,
        "refund_count_by_intent": {
            intent: len(same_intent) for intent, same_intent in sorted(commits_by_intent.items())
        },
        "committed_cents_by_order": dict(sorted(committed_cents_by_order.items())),
        "state_change_seqs": [event.seq for event in commits],
        "transaction_ids": [event.transaction_id for event in commits],
        "timeout_seqs": [
            event.seq for event in ordered if event.event_type == EventType.NETWORK_TIMEOUT
        ],
        "idempotent_replay_seqs": [event.seq for event in replays],
        "duplicate_refund_seqs": duplicate_refund_seqs,
        "phantom_success_seqs": phantom_success_seqs,
        "misrouted_write_seqs": misrouted_write_seqs,
        "amount_mismatch_seqs": amount_mismatch_seqs,
        "first_bad_event_seq": anomaly_seqs[0] if anomaly_seqs else first_chain_error,
    }


def propose_ground_truth(
    case_id: str,
    family_id: str,
    events: Iterable[LedgerEvent],
    *,
    external_claim_expected: bool = False,
) -> GroundTruth:
    """Build a deterministic, explicitly unverified ground-truth proposal."""
    facts = derive_ledger_facts(events)
    expected_claims: list[dict[str, Any]] = []

    anomaly_specs = (
        ("duplicate_refund_seqs", ClaimType.COUNT, "multiple commits for one intent"),
        ("phantom_success_seqs", ClaimType.REFUND_ISSUED, "success reported without a commit"),
        ("misrouted_write_seqs", ClaimType.ORDER_REF, "commit landed on another order"),
        ("amount_mismatch_seqs", ClaimType.AMOUNT, "committed amount differs from requested amount"),
    )
    for fact_name, claim_type, note in anomaly_specs:
        seqs = facts[fact_name]
        if seqs:
            expected_claims.append(
                {
                    "claim_type": claim_type,
                    "status": Status.CONTRADICTED,
                    "evidence_seqs": list(seqs),
                    "note": note,
                }
            )

    if external_claim_expected:
        expected_claims.append(
            {
                "claim_type": ClaimType.EXTERNAL_SIDE_EFFECT,
                "status": Status.UNVERIFIABLE,
                "evidence_seqs": [],
                "note": "the configured ledger cannot observe this external side effect",
            }
        )

    if not expected_claims:
        expected_claims.append(
            {
                "claim_type": ClaimType.REFUND_ISSUED,
                "status": Status.SUPPORTED,
                "evidence_seqs": list(facts["state_change_seqs"]),
                "note": "no deterministic ledger anomaly was found",
            }
        )
    verdict = aggregate_verdict(claim["status"] for claim in expected_claims)
    return GroundTruth(
        case_id=case_id,
        family_id=family_id,
        verdict=verdict,
        first_bad_event_seq=facts["first_bad_event_seq"],
        expected_claims=expected_claims,
        ledger_facts=facts,
        verified_by_human=False,
        notes="Provisional ledger-derived proposal; claim-aware human verification is still required.",
    )


__all__ = ["derive_ledger_facts", "propose_ground_truth"]
