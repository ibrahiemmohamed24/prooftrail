import pytest

from prooftrail.env.faults import FaultInjector, FaultKind, FaultSpec


def test_spec_validation():
    with pytest.raises(ValueError):
        FaultSpec("explode", "issue_refund")
    with pytest.raises(ValueError):
        FaultSpec(FaultKind.PHANTOM_SUCCESS, "issue_refund", nth_call=0)


def test_fires_only_on_nth_call_of_that_tool():
    inj = FaultInjector([FaultSpec(FaultKind.TIMEOUT_AFTER_COMMIT, "issue_refund", nth_call=1)])

    # unrelated tool never fires
    i = inj.record_call("lookup_order")
    assert inj.active("lookup_order", i, "tc_0") is None

    i1 = inj.record_call("issue_refund")
    assert i1 == 1
    spec = inj.active("issue_refund", i1, "tc_1")
    assert spec is not None and spec.kind == FaultKind.TIMEOUT_AFTER_COMMIT

    i2 = inj.record_call("issue_refund")
    assert i2 == 2
    assert inj.active("issue_refund", i2, "tc_2") is None, "retry must run clean"

    assert inj.calls_so_far("issue_refund") == 2
    assert inj.calls_so_far("send_email") == 0


def test_fired_log_names_tool_call():
    inj = FaultInjector([FaultSpec(FaultKind.AMOUNT_DRIFT, "issue_refund", params={"delta_cents": -1000})])
    i = inj.record_call("issue_refund")
    inj.active("issue_refund", i, "tc_9")
    assert inj.describe() == [
        {"kind": "amount_drift", "tool": "issue_refund", "nth_call": 1, "tool_call_id": "tc_9",
         "params": {"delta_cents": -1000}}
    ]


def test_no_specs_never_fires():
    inj = FaultInjector()
    for n in range(5):
        i = inj.record_call("issue_refund")
        assert inj.active("issue_refund", i, f"tc_{n}") is None
    assert inj.fired == []
