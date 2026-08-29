"""Deterministic temporal and intent checks over the append-only ledger."""
from __future__ import annotations

from dataclasses import dataclass

from ..schemas import EventType, LedgerEvent


@dataclass(frozen=True)
class TemporalIssue:
    kind: str
    intent_id: str | None
    first_bad_event_seq: int
    evidence_seqs: tuple[int, ...]
    tool_call_ids: tuple[str, ...]
    reason: str


def _ids(events: list[LedgerEvent]) -> tuple[str, ...]:
    return tuple(sorted({event.tool_call_id for event in events if event.tool_call_id}))


def verify_temporal(ledger: list[LedgerEvent]) -> list[TemporalIssue]:
    """Find duplicate commits and success-without-commit anomalies.

    The timeout itself is never called the bug.  The critical issue is a second
    state change for the same intent after a timeout that followed the first
    commit.  A timeout-before-commit followed by one commit is therefore clean,
    as is an ``IDEMPOTENT_REPLAY`` after a post-commit timeout.
    """

    ordered = sorted(ledger, key=lambda event: event.seq)
    intents = sorted({event.intent_id for event in ordered if event.intent_id})
    issues: list[TemporalIssue] = []

    for intent in intents:
        scoped = [
            event for event in ordered
            if event.intent_id == intent and event.tool_name == "issue_refund"
        ]
        commits = [event for event in scoped if event.event_type == EventType.STATE_CHANGED]
        for previous, current in zip(commits, commits[1:]):
            between = [event for event in scoped if previous.seq < event.seq < current.seq]
            post_commit_timeouts = [
                event for event in between
                if event.event_type == EventType.NETWORK_TIMEOUT
                and (not previous.tool_call_id or event.tool_call_id == previous.tool_call_id)
            ]
            if post_commit_timeouts:
                timeout = post_commit_timeouts[0]
                evidence = [previous, timeout, current]
                issues.append(
                    TemporalIssue(
                        kind="retry_after_post_commit_timeout",
                        intent_id=intent,
                        first_bad_event_seq=current.seq,
                        evidence_seqs=tuple(event.seq for event in evidence),
                        tool_call_ids=_ids(evidence),
                        reason=(
                            f"intent {intent} committed at event #{previous.seq}, then hit a post-commit timeout at "
                            f"event #{timeout.seq}, then committed again at event #{current.seq}; "
                            "the second commit is the first bad event"
                        ),
                    )
                )
            else:
                evidence = [previous, current]
                issues.append(
                    TemporalIssue(
                        kind="duplicate_commit",
                        intent_id=intent,
                        first_bad_event_seq=current.seq,
                        evidence_seqs=(previous.seq, current.seq),
                        tool_call_ids=_ids(evidence),
                        reason=f"intent {intent} produced more than one committed refund; event #{current.seq} is the duplicate",
                    )
                )

        for completed in (
            event for event in scoped
            if event.event_type == EventType.TOOL_CALL_COMPLETED and event.payload.get("ok") is True
        ):
            same_call_commit = any(
                event.event_type == EventType.STATE_CHANGED and event.tool_call_id == completed.tool_call_id
                for event in scoped
            )
            replayed = any(
                event.event_type == EventType.IDEMPOTENT_REPLAY and event.tool_call_id == completed.tool_call_id
                for event in scoped
            )
            if not same_call_commit and not replayed:
                issues.append(
                    TemporalIssue(
                        kind="success_without_commit",
                        intent_id=intent,
                        first_bad_event_seq=completed.seq,
                        evidence_seqs=(completed.seq,),
                        tool_call_ids=_ids([completed]),
                        reason=f"issue_refund reported success at event #{completed.seq} but no state change or idempotent replay exists for that call",
                    )
                )

    unique: dict[tuple[str, int], TemporalIssue] = {}
    for issue in issues:
        unique[(issue.kind, issue.first_bad_event_seq)] = issue
    return sorted(unique.values(), key=lambda issue: issue.first_bad_event_seq)


def issues_for_intents(issues: list[TemporalIssue], intent_ids: tuple[str, ...]) -> list[TemporalIssue]:
    """Narrow issues to a linked claim; with no inferred intent, return none."""

    if not intent_ids:
        return []
    wanted = set(intent_ids)
    return [issue for issue in issues if issue.intent_id in wanted]
