"""Render a reviewable Evidence Certificate from ``AuditOutput``."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ..schemas import AgentTrace, AuditOutput, ClaimType, LedgerEvent


def _event_dict(event: LedgerEvent) -> dict[str, Any]:
    return {
        "event_seq": event.seq,
        "event_type": event.event_type,
        "timestamp": event.ts,
        "intent_id": event.intent_id,
        "tool_name": event.tool_name,
        "tool_call_id": event.tool_call_id,
        "transaction_id": event.transaction_id,
        "idempotency_key": event.idempotency_key,
        "entity": event.entity,
        "state_before": event.state_before,
        "state_after": event.state_after,
        "payload": event.payload,
    }


def _tool_calls_for_claim(claim: dict[str, Any], evidence: list[LedgerEvent], trace: AgentTrace) -> list[dict[str, Any]]:
    ids = {event.tool_call_id for event in evidence if event.tool_call_id}
    if claim["claim_type"] == ClaimType.EXTERNAL_SIDE_EFFECT:
        ids.update(call.tool_call_id for call in trace.tool_calls if call.tool_name in {"send_email", "open_ticket"})
    return [asdict(call) for call in trace.tool_calls if call.tool_call_id in ids]


def build_certificate(output: AuditOutput, trace: AgentTrace, ledger: list[LedgerEvent]) -> dict[str, Any]:
    """Build the JSON-ready certificate, including exact linked state snapshots."""

    by_seq = {event.seq: event for event in ledger}
    claim_rows: list[dict[str, Any]] = []
    for claim in output.claims:
        evidence = [by_seq[seq] for seq in claim.evidence_seqs if seq in by_seq]
        row = asdict(claim)
        row["events"] = [_event_dict(event) for event in evidence]
        row["tool_calls"] = _tool_calls_for_claim(row, evidence, trace)
        claim_rows.append(row)
    cited, total = output.evidence_coverage
    return {
        "certificate_version": 1,
        "case_id": output.case_id,
        "auditor": output.auditor,
        "verdict": output.verdict,
        "first_bad_event_seq": output.first_bad_event_seq,
        "explanation": output.explanation,
        "evidence_coverage": {"cited": cited, "total": total},
        "usage": output.usage,
        "claims": claim_rows,
    }


def render_certificate_json(
    output: AuditOutput,
    trace: AgentTrace,
    ledger: list[LedgerEvent],
    *,
    indent: int = 2,
) -> str:
    """Render a stable UTF-8 JSON certificate."""

    return json.dumps(build_certificate(output, trace, ledger), indent=indent, sort_keys=True, ensure_ascii=False)


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_certificate_markdown(output: AuditOutput, trace: AgentTrace, ledger: list[LedgerEvent]) -> str:
    """Render a compact certificate an operations reviewer can sign off."""

    certificate = build_certificate(output, trace, ledger)
    cited = certificate["evidence_coverage"]["cited"]
    total = certificate["evidence_coverage"]["total"]
    lines = [
        f"# ProofTrail Evidence Certificate — {_cell(output.case_id)}",
        "",
        f"- **Verdict:** `{output.verdict}`",
        f"- **First bad event:** `{output.first_bad_event_seq}`" if output.first_bad_event_seq is not None else "- **First bad event:** none",
        f"- **Evidence coverage:** `{cited}/{total}` claims",
        f"- **Summary:** {_cell(output.explanation)}",
        "",
        "## Claims",
        "",
        "| Claim | Type | Verdict | Evidence | Reason |",
        "|---|---|---|---|---|",
    ]
    for claim in certificate["claims"]:
        refs = ", ".join(f"#{seq}" for seq in claim["evidence_seqs"]) or "—"
        lines.append(
            f"| {_cell(claim['claim_text'])} | `{claim['claim_type']}` | `{claim['status']}` | {_cell(refs)} | {_cell(claim['reason'])} |"
        )

    lines.extend(["", "## Linked evidence", ""])
    any_evidence = False
    seen: set[int] = set()
    for claim in certificate["claims"]:
        for event in claim["events"]:
            if event["event_seq"] in seen:
                continue
            seen.add(event["event_seq"])
            any_evidence = True
            lines.extend(
                [
                    f"### Event #{event['event_seq']} — `{event['event_type']}`",
                    "",
                    f"- **Intent / call / transaction:** `{_cell(event['intent_id'])}` / `{_cell(event['tool_call_id'])}` / `{_cell(event['transaction_id'])}`",
                    f"- **Entity:** `{_cell(event['entity'])}`",
                    f"- **State before:** `{_cell(event['state_before'])}`",
                    f"- **State after:** `{_cell(event['state_after'])}`",
                    f"- **Payload:** `{_cell(event['payload'])}`",
                    "",
                ]
            )
    if not any_evidence:
        lines.append("No independently ledgered event could be linked to this claim.")

    tool_calls: dict[str, dict[str, Any]] = {}
    for claim in certificate["claims"]:
        for call in claim["tool_calls"]:
            tool_calls[call["tool_call_id"]] = call
    if tool_calls:
        lines.extend(["", "## Agent-visible tool calls", ""])
        for call_id, call in sorted(tool_calls.items()):
            lines.extend(
                [
                    f"- `{call_id}` / `{call['tool_name']}` — args `{_cell(call['args'])}`; result `{_cell(call['result'])}`; error `{_cell(call['error'])}`",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"
