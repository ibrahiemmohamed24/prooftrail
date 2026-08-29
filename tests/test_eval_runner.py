from prooftrail.eval.runner import run_auditor
from prooftrail.schemas.trace import AgentTrace, FrozenCase
from prooftrail.schemas.verdict import AuditOutput, Status


def _case(case_id):
    return FrozenCase(
        case_id=case_id,
        family_id="F01",
        seed=0,
        trace=AgentTrace(case_id, "offline", "sha", [], [], [], "Nothing to report"),
        ledger=[],
    )


class DummyAuditor:
    name = "dummy"

    def audit(self, case):
        return AuditOutput(case.case_id, self.name, Status.UNVERIFIABLE, [], None)


def test_runner_preserves_case_identity():
    outputs = run_auditor([_case("a"), _case("b")], DummyAuditor())
    assert list(outputs) == ["a", "b"]


def test_runner_rejects_duplicate_cases():
    try:
        run_auditor([_case("a"), _case("a")], DummyAuditor())
    except ValueError as exc:
        assert "duplicate case_id" in str(exc)
    else:
        raise AssertionError("duplicates must fail")
