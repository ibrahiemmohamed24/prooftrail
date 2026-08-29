"""One-command, zero-network demonstration of ProofTrail's killer case."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agent import RefundAgent, ScriptedModelClient, build_refund_tool_actions
from .auditor import ProofTrailPipeline, render_certificate_json, render_certificate_markdown
from .eval.runner import write_outputs
from .scenarios import generate_scenario, propose_ground_truth
from .schemas import AuditOutput, FrozenCase, GroundTruth


@dataclass(frozen=True)
class DemoRun:
    case: FrozenCase
    audit: AuditOutput
    ground_truth: GroundTruth
    primary_order_state: dict[str, Any]
    ledger_chain_valid: bool

    def summary(self) -> dict[str, Any]:
        facts = self.ground_truth.ledger_facts
        refund_counts = facts.get("refund_count_by_intent", {})
        return {
            "case_id": self.case.case_id,
            "mode": "scripted-offline-demo-not-a-real-llm-run",
            "agent_claim": self.case.trace.final_report,
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


def run_killer_demo(*, seed: int = 0) -> DemoRun:
    """Run F02 end-to-end with an explicit scripted blind-retry fixture.

    The scripted client is only a deterministic development/replay fixture.
    It is deliberately not presented as the real-model benchmark dataset.
    """

    scenario = generate_scenario("F02", seed)
    try:
        request = scenario.user_requests[0]
        order = scenario.seeded.orders[0]
        order_id = order["order_id"]
        amount_cents = order["amount_cents"]
        scenario.record_user_intent(0)

        client = ScriptedModelClient.blind_refund_retry_demo(
            order_id=order_id,
            intent_id=request.intent_id,
            amount_cents=amount_cents,
        )
        tools = build_refund_tool_actions(
            scenario.tools,
            lambda: _last_sequence(scenario),
        )
        trace = RefundAgent(client, tools).run(
            case_id=scenario.case_id,
            user_requests=(request.to_dict(),),
        )
        ledger = scenario.ledger.events()
        chain_valid, _ = scenario.ledger.verify_chain()
        final_state = scenario.db.snapshot_order(order_id)
        if final_state is None:
            raise RuntimeError(f"demo order {order_id} disappeared")
    finally:
        scenario.close()

    case = FrozenCase(
        case_id=scenario.case_id,
        family_id=scenario.family.family_id,
        seed=seed,
        trace=trace,
        ledger=ledger,
    )
    audit = ProofTrailPipeline().audit(case)
    truth = propose_ground_truth(case.case_id, case.family_id, ledger)
    return DemoRun(case, audit, truth, final_state, chain_valid)


def write_demo_artifacts(run: DemoRun, output_dir: str | Path) -> dict[str, Path]:
    """Persist the complete evidence bundle and review certificate."""

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
    paths["case"].write_text(
        json.dumps(run.case.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["labels"].write_text(
        json.dumps(run.ground_truth.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_outputs(paths["audit"], {run.case.case_id: run.audit})
    paths["certificate_json"].write_text(
        render_certificate_json(run.audit, run.case.trace, run.case.ledger) + "\n",
        encoding="utf-8",
    )
    paths["certificate_markdown"].write_text(
        render_certificate_markdown(run.audit, run.case.trace, run.case.ledger),
        encoding="utf-8",
    )
    paths["summary"].write_text(
        json.dumps(run.summary(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return paths


__all__ = ["DemoRun", "run_killer_demo", "write_demo_artifacts"]
