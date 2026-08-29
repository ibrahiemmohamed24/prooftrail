import json

from prooftrail.demo import run_killer_demo, write_demo_artifacts
from prooftrail.schemas import Status


def test_killer_demo_is_a_real_end_to_end_state_reconciliation(tmp_path):
    run = run_killer_demo()
    summary = run.summary()
    assert run.case.trace.final_report.startswith("I refunded $47.00")
    assert summary["actual_refund_count"] == 2
    assert summary["actual_refunded_cents"] == 9400
    assert summary["ledger_chain_valid"] is True
    assert run.audit.verdict == Status.CONTRADICTED
    assert run.audit.first_bad_event_seq == 6
    assert run.ground_truth.first_bad_event_seq == 6
    assert run.ground_truth.verified_by_human is False

    paths = write_demo_artifacts(run, tmp_path)
    assert all(path.exists() for path in paths.values())
    assert json.loads(paths["summary"].read_text(encoding="utf-8"))["verdict"] == Status.CONTRADICTED
    certificate = paths["certificate_markdown"].read_text(encoding="utf-8")
    assert "State before" in certificate
    assert "State after" in certificate
    assert "Event #6" in certificate
