"""Link an extracted claim to raw trace calls and ledger rows.

Linking deliberately happens before verdict assignment.  It is deterministic
and preserves both views of a call: what the agent saw in ``ToolCallRecord`` and
what the append-only ledger proves through ``LedgerEvent``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import AgentTrace, ClaimType, EventType, LedgerEvent, ToolCallRecord
from .claim_extractor import ExtractedClaim


_REFUND_TERMINALS = {
    EventType.TOOL_CALL_COMPLETED,
    EventType.TOOL_CALL_FAILED,
    EventType.NETWORK_TIMEOUT,
    EventType.IDEMPOTENT_REPLAY,
}


def _normalise_order(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.casefold().startswith("order:"):
        text = text.split(":", 1)[1]
    return text.casefold()


def _call_order(call: ToolCallRecord) -> str | None:
    for key in ("order_id", "requested_order_id", "order"):
        if key in call.args:
            return _normalise_order(call.args[key])
    return None


def _event_mentions_order(event: LedgerEvent, order_id: str) -> bool:
    wanted = _normalise_order(order_id)
    if _normalise_order(event.entity) == wanted:
        return True
    for key in ("order_id", "requested_order_id", "target_order_id"):
        if _normalise_order(event.payload.get(key)) == wanted:
            return True
    return False


@dataclass(frozen=True)
class LinkedEvidence:
    claim: ExtractedClaim
    intent_ids: tuple[str, ...]
    tool_calls: tuple[ToolCallRecord, ...]
    events: tuple[LedgerEvent, ...]
    commit_events: tuple[LedgerEvent, ...]
    terminal_events: tuple[LedgerEvent, ...]

    @property
    def tool_call_ids(self) -> tuple[str, ...]:
        ids = {call.tool_call_id for call in self.tool_calls}
        ids.update(event.tool_call_id for event in self.events if event.tool_call_id)
        return tuple(sorted(ids))

    @property
    def event_seqs(self) -> tuple[int, ...]:
        return tuple(sorted({event.seq for event in self.events}))


def _infer_intents(claim: ExtractedClaim, trace: AgentTrace) -> set[str]:
    intents: set[str] = set()
    wanted_order = _normalise_order(claim.order_id)
    if wanted_order:
        intents.update(call.intent_id for call in trace.tool_calls if _call_order(call) == wanted_order)
        for request in trace.user_requests:
            text = str(request.get("text", "")).casefold()
            if wanted_order in text and request.get("intent_id"):
                intents.add(str(request["intent_id"]))

    if claim.claim_type == ClaimType.EXTERNAL_SIDE_EFFECT:
        intents.update(call.intent_id for call in trace.tool_calls if call.tool_name in {"send_email", "open_ticket"})

    if not intents:
        trace_intents = {
            str(request["intent_id"])
            for request in trace.user_requests
            if request.get("intent_id")
        }
        if len(trace_intents) == 1:
            intents.update(trace_intents)

    if not intents and claim.claim_type in {
        ClaimType.REFUND_ISSUED,
        ClaimType.REFUND_NOT_ISSUED,
        ClaimType.AMOUNT,
        ClaimType.ORDER_REF,
        ClaimType.COUNT,
    }:
        refund_intents = {call.intent_id for call in trace.tool_calls if call.tool_name == "issue_refund"}
        if len(refund_intents) == 1:
            intents.update(refund_intents)
    return intents


def link_claim(claim: ExtractedClaim, trace: AgentTrace, ledger: list[LedgerEvent]) -> LinkedEvidence:
    """Return all evidence that can be deterministically tied to ``claim``."""

    intents = _infer_intents(claim, trace)
    external_tools = {"send_email", "open_ticket"}
    if claim.claim_type == ClaimType.EXTERNAL_SIDE_EFFECT:
        calls = tuple(
            call for call in trace.tool_calls
            if call.tool_name in external_tools and (not intents or call.intent_id in intents)
        )
    else:
        calls = tuple(
            call for call in trace.tool_calls
            if call.tool_name == "issue_refund"
            and (not intents or call.intent_id in intents)
            and (not claim.order_id or _call_order(call) == _normalise_order(claim.order_id) or call.intent_id in intents)
        )
    call_ids = {call.tool_call_id for call in calls}

    related: list[LedgerEvent] = []
    for event in sorted(ledger, key=lambda item: item.seq):
        by_intent = bool(event.intent_id and event.intent_id in intents)
        by_call = bool(event.tool_call_id and event.tool_call_id in call_ids)
        by_order = bool(claim.order_id and _event_mentions_order(event, claim.order_id))
        by_external_tool = claim.claim_type == ClaimType.EXTERNAL_SIDE_EFFECT and event.tool_name in external_tools
        if by_intent or by_call or by_order or by_external_tool:
            related.append(event)

    commits = tuple(
        event for event in related
        if event.event_type == EventType.STATE_CHANGED and event.tool_name == "issue_refund"
    )
    terminals = tuple(
        event for event in related
        if event.tool_name == "issue_refund" and event.event_type in _REFUND_TERMINALS
    )
    return LinkedEvidence(
        claim=claim,
        intent_ids=tuple(sorted(intents)),
        tool_calls=calls,
        events=tuple(related),
        commit_events=commits,
        terminal_events=terminals,
    )
