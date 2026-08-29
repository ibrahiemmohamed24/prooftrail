"""Run one scenario instance end to end with any ``ModelClient``.

The same code path serves the scripted demo, live recording and offline
replay, so the only thing that differs between them is the model adapter.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..auditor import ProofTrailPipeline, render_certificate_json, render_certificate_markdown
from ..eval.runner import write_outputs
from ..scenarios import generate_scenario, propose_ground_truth
from ..schemas import AuditOutput, FrozenCase, GroundTruth
from .interfaces import ModelClient
from .refund_agent import RefundAgent
from .tool_defs import build_refund_tool_actions

MODE_SCRIPTED = "scripted-offline-demo-not-a-real-llm-run"
MODE_LIVE = "live-llm-run"
MODE_REPLAY = "replay-from-cache-no-network"


@dataclass(frozen=True)
class CaseRun:
    case: FrozenCase
    audit: AuditOutput
    ground_truth: GroundTruth
    order_states: dict[str, dict[str, Any]]
    ledger_chain_valid: bool
    mode: str
    scenario_metadata: dict[str, Any]

    @property
    def primary_order_state(self) -> dict[str, Any]:
        first_order = self.scenario_metadata["seeded"]["orders"][0]["order_id"]
        return self.order_states[first_order]

    def summary(self) -> dict[str, Any]:
        facts = self.ground_truth.ledger_facts
        refund_counts = facts.get("refund_count_by_intent", {})
        trace = self.case.trace
        return {
            "case_id": self.case.case_id,
            "mode": self.mode,
            "model": trace.model,
            "agent_claim": trace.final_report,
            "stop_reason": trace.stop_reason,
            "tool_call_count": len(trace.tool_calls),
            "usage": trace.usage.to_dict(),
            "actual_refund_count": sum(refund_counts.values()),
            "actual_refunded_cents": self.primary_order_state["refunded_cents"],
            "verdict": self.audit.verdict,
            "first_bad_event_seq": self.audit.first_bad_event_seq,
            "ledger_event_count": len(self.case.ledger),
            "ledger_chain_valid": self.ledger_chain_valid,
            "labels_human_verified": self.ground_truth.verified_by_human,
        }


def _last_sequence(scenario) -> int | None:
    event = scenario.ledger.last()
    return event.seq if event is not None else None


def run_case(family: str, seed: int, *, model_client: ModelClient, mode: str) -> CaseRun:
    """Generate ``family x seed``, run the agent, audit it and derive labels."""

    scenario = generate_scenario(family, seed)
    try:
        tools = build_refund_tool_actions(scenario.tools, lambda: _last_sequence(scenario))
        agent = RefundAgent(model_client, tools)
        trace = agent.run(
            case_id=scenario.case_id,
            user_requests=tuple(request.to_dict() for request in scenario.user_requests),
            on_request=lambda ordinal, _request: scenario.record_user_intent(ordinal),
        )
        ledger = scenario.ledger.events()
        chain_valid, _ = scenario.ledger.verify_chain()
        order_states: dict[str, dict[str, Any]] = {}
        for order in scenario.seeded.orders:
            state = scenario.db.snapshot_order(order["order_id"])
            if state is None:
                raise RuntimeError(f"order {order['order_id']} disappeared during the run")
            order_states[order["order_id"]] = state
        metadata = scenario.metadata()
        family_id = scenario.family.family_id
    finally:
        scenario.close()

    case = FrozenCase(
        case_id=metadata["case_id"],
        family_id=family_id,
        seed=seed,
        trace=trace,
        ledger=ledger,
    )
    audit = ProofTrailPipeline().audit(case)
    # Whether an out-of-ledger claim is expected is read from what the agent
    # actually did (it called the unledgered tool), never from the family.
    external_claim = any(record.tool_name == "send_email" for record in trace.tool_calls)
    truth = propose_ground_truth(
        case.case_id, case.family_id, ledger, external_claim_expected=external_claim
    )
    return CaseRun(case, audit, truth, order_states, chain_valid, mode, metadata)


def write_case_artifacts(run: CaseRun, output_dir: str | Path) -> dict[str, Path]:
    """Persist the evidence bundle, provisional labels and certificate."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "case": directory / "case.json",
        "labels": directory / "labels.provisional.json",
        "audit": directory / "audit.json",
        "certificate_json": directory / "certificate.json",
        "certificate_markdown": directory / "certificate.md",
        "summary": directory / "summary.json",
    }
    _dump(paths["case"], run.case.to_dict())
    _dump(paths["labels"], run.ground_truth.to_dict())
    write_outputs(paths["audit"], {run.case.case_id: run.audit})
    paths["certificate_json"].write_text(
        render_certificate_json(run.audit, run.case.trace, run.case.ledger) + "\n",
        encoding="utf-8",
    )
    paths["certificate_markdown"].write_text(
        render_certificate_markdown(run.audit, run.case.trace, run.case.ledger),
        encoding="utf-8",
    )
    _dump(paths["summary"], run.summary())
    return paths


def _dump(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "MODE_LIVE",
    "MODE_REPLAY",
    "MODE_SCRIPTED",
    "CaseRun",
    "run_case",
    "write_case_artifacts",
]
