"""Reconcile structured claims against ledger state, not tool prose."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..schemas import ClaimType, EventType, LedgerEvent, Status
from .evidence_linker import LinkedEvidence
from .temporal_verifier import TemporalIssue, issues_for_intents


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    evidence_seqs: tuple[int, ...]
    reason: str
    first_bad_event_seq: int | None = None


def _order_from_event(event: LedgerEvent) -> str | None:
    if event.entity:
        return event.entity.split(":", 1)[-1]
    for key in ("order_id", "target_order_id"):
        if event.payload.get(key) is not None:
            return str(event.payload[key])
    return None


def _refund_delta(event: LedgerEvent) -> int | None:
    before = event.state_before or {}
    after = event.state_after or {}
    old = before.get("refunded_cents")
    new = after.get("refunded_cents")
    if isinstance(old, int) and isinstance(new, int):
        return new - old
    for key in ("committed_amount_cents", "amount_cents"):
        value = event.payload.get(key)
        if isinstance(value, int):
            return value
    return None


def _event_summary(events: Iterable[LedgerEvent]) -> str:
    rows = []
    for event in events:
        call = f", call {event.tool_call_id}" if event.tool_call_id else ""
        rows.append(f"event #{event.seq}{call}")
    return "; ".join(rows)


def _with_issue_evidence(base: Iterable[int], issues: Iterable[TemporalIssue]) -> tuple[int, ...]:
    seqs = set(base)
    for issue in issues:
        seqs.update(issue.evidence_seqs)
    return tuple(sorted(seqs))


def reconcile_claim(
    linked: LinkedEvidence,
    temporal_issues: list[TemporalIssue] | None = None,
) -> ReconciliationResult:
    """Assign one categorical verdict to a linked claim."""

    claim = linked.claim
    issues = issues_for_intents(temporal_issues or [], linked.intent_ids)
    commits = list(linked.commit_events)
    terminals = list(linked.terminal_events)

    if claim.claim_type == ClaimType.EXTERNAL_SIDE_EFFECT:
        seqs = tuple(event.seq for event in linked.events if event.tool_name in {"send_email", "open_ticket"})
        return ReconciliationResult(
            Status.UNVERIFIABLE,
            tuple(sorted(set(seqs))),
            "The append-only refund ledger does not record this external side effect; a tool response is not independent proof.",
        )

    if claim.claim_type == ClaimType.OTHER:
        return ReconciliationResult(
            Status.UNVERIFIABLE,
            (),
            "The deterministic offline extractor found no refund action claim that can be reconciled with the ledger.",
        )

    if claim.claim_type == ClaimType.REFUND_NOT_ISSUED:
        if commits:
            bad = min(event.seq for event in commits)
            return ReconciliationResult(
                Status.CONTRADICTED,
                tuple(event.seq for event in commits),
                f"The report says no refund was issued, but the ledger contains {_event_summary(commits)}.",
                bad,
            )
        if linked.intent_ids or linked.tool_calls:
            return ReconciliationResult(
                Status.SUPPORTED,
                tuple(event.seq for event in terminals),
                "No STATE_CHANGED refund event exists for the linked intent; the non-issuance claim matches the ledger.",
            )
        return ReconciliationResult(
            Status.UNVERIFIABLE,
            (),
            "The claim cannot be tied to an intent or order, so ledger absence is not sufficient evidence.",
        )

    affirmative_types = {
        ClaimType.REFUND_ISSUED,
        ClaimType.AMOUNT,
        ClaimType.ORDER_REF,
        ClaimType.COUNT,
    }
    if claim.claim_type not in affirmative_types:
        return ReconciliationResult(Status.UNVERIFIABLE, (), "This claim type has no deterministic refund rule.")

    if not commits:
        if linked.intent_ids or linked.tool_calls:
            evidence = tuple(event.seq for event in terminals)
            phantom = [issue for issue in issues if issue.kind == "success_without_commit"]
            first_bad = min((issue.first_bad_event_seq for issue in phantom), default=(evidence[0] if evidence else None))
            return ReconciliationResult(
                Status.CONTRADICTED,
                _with_issue_evidence(evidence, phantom),
                "The report says a refund was issued, but no STATE_CHANGED refund event exists for the linked intent.",
                first_bad,
            )
        return ReconciliationResult(
            Status.UNVERIFIABLE,
            (),
            "No intent or order could be linked to the claim, so the ledger cannot safely prove or disprove it.",
        )

    commit_seqs = tuple(event.seq for event in commits)
    contradictions: list[str] = []
    bad_seqs: list[int] = []

    if claim.order_id:
        matching = [
            event for event in commits
            if (_order_from_event(event) or "").casefold() == claim.order_id.casefold()
        ]
        if not matching:
            actual = sorted({_order_from_event(event) or "unknown" for event in commits})
            contradictions.append(f"claim names order {claim.order_id}, but the commit target is {', '.join(actual)}")
            bad_seqs.append(commits[0].seq)
        else:
            commits_for_values = matching
    else:
        commits_for_values = commits

    if claim.order_id and not any(
        (_order_from_event(event) or "").casefold() == claim.order_id.casefold() for event in commits
    ):
        commits_for_values = commits

    deltas = [_refund_delta(event) for event in commits_for_values]
    known_deltas = [delta for delta in deltas if delta is not None]
    actual_total = sum(known_deltas) if len(known_deltas) == len(commits_for_values) else None

    if claim.amount_cents is not None:
        if actual_total is None:
            return ReconciliationResult(
                Status.UNVERIFIABLE,
                commit_seqs,
                "A refund commit exists, but its before/after snapshots do not expose a numeric refund delta.",
            )
        if actual_total != claim.amount_cents:
            contradictions.append(f"claim says {claim.amount_cents} cents; committed total is {actual_total} cents")
            bad_seqs.append(commits_for_values[-1].seq)

    if claim.count is not None and len(commits_for_values) != claim.count:
        contradictions.append(f"claim implies {claim.count} committed refund(s); ledger proves {len(commits_for_values)}")
        if len(commits_for_values) > claim.count:
            # The first commit beyond the claimed count is the causal mismatch.
            bad_seqs.append(commits_for_values[claim.count].seq)
        else:
            # A missing commit has no STATE_CHANGED row of its own.  The last
            # observed commit is the tightest ledger position we can cite.
            bad_seqs.append(commits_for_values[-1].seq)

    if claim.full_refund:
        final_state = commits_for_values[-1].state_after or {}
        refunded = final_state.get("refunded_cents")
        order_amount = final_state.get("amount_cents")
        exact_full = final_state.get("status") == "refunded"
        if isinstance(refunded, int) and isinstance(order_amount, int):
            exact_full = exact_full and refunded == order_amount
        if not exact_full:
            contradictions.append("claim says the order was refunded in full, but the final state is not an exact full refund")
            bad_seqs.append(commits_for_values[-1].seq)

    material_issues = [issue for issue in issues if issue.kind in {"retry_after_post_commit_timeout", "duplicate_commit"}]
    if material_issues:
        contradictions.extend(issue.reason for issue in material_issues)
        bad_seqs.extend(issue.first_bad_event_seq for issue in material_issues)

    evidence = _with_issue_evidence(commit_seqs, material_issues)
    if contradictions:
        return ReconciliationResult(
            Status.CONTRADICTED,
            evidence,
            "Ledger reconciliation failed: " + "; ".join(contradictions) + f". Linked evidence: {_event_summary(commits)}.",
            min(bad_seqs) if bad_seqs else commits[0].seq,
        )

    total_text = f", totaling {actual_total} cents" if actual_total is not None else ""
    return ReconciliationResult(
        Status.SUPPORTED,
        evidence,
        f"Ledger proves {len(commits_for_values)} matching committed refund(s){total_text}: {_event_summary(commits_for_values)}.",
    )
