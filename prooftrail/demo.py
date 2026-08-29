"""One-command, zero-network demonstration of ProofTrail's killer case."""
from __future__ import annotations

from pathlib import Path

from .agent import ScriptedModelClient
from .agent.runner import MODE_SCRIPTED, CaseRun, run_case, write_case_artifacts
from .scenarios import generate_scenario

# Backwards-compatible names: the demo run is simply a scripted ``CaseRun``.
DemoRun = CaseRun


def run_killer_demo(*, seed: int = 0) -> CaseRun:
    """Run F02 end-to-end with an explicit scripted blind-retry fixture.

    The scripted client is only a deterministic development/replay fixture.
    It is deliberately not presented as the real-model benchmark dataset.
    """

    # Peek at the deterministic seed data to build the fixture's arguments.
    preview = generate_scenario("F02", seed)
    try:
        request = preview.user_requests[0]
        order = preview.seeded.orders[0]
        client = ScriptedModelClient.blind_refund_retry_demo(
            order_id=order["order_id"],
            intent_id=request.intent_id,
            amount_cents=order["amount_cents"],
        )
    finally:
        preview.close()

    return run_case("F02", seed, model_client=client, mode=MODE_SCRIPTED)


def write_demo_artifacts(run: CaseRun, output_dir: str | Path) -> dict[str, Path]:
    """Persist the complete evidence bundle and review certificate."""

    return write_case_artifacts(run, output_dir)


__all__ = ["DemoRun", "run_killer_demo", "write_demo_artifacts"]
