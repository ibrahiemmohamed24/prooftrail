from __future__ import annotations

import pytest

from prooftrail.env import IdempotencyConflict, ToolTimeout
from prooftrail.ids import tool_call_id
from prooftrail.scenarios import generate_scenario
from prooftrail.schemas import EventType


@pytest.fixture
def scenario_factory():
    made = []

    def factory(family_id: str, seed: int = 0):
        scenario = generate_scenario(family_id, seed)
        made.append(scenario)
        return scenario

    yield factory
    for scenario in made:
        scenario.close()


def _start(scenario, ordinal: int = 0):
    scenario.record_user_intent(ordinal)
    return scenario.user_requests[ordinal]


def _refund(scenario, request, attempt: int, *, order_index: int = 0, key: str | None = None):
    order = scenario.seeded.orders[order_index]
    return scenario.tools.issue_refund(
        order["order_id"],
        order["amount_cents"],
        intent_id=request.intent_id,
        tool_call_id=tool_call_id(scenario.case_id, attempt),
        idempotency_key=key,
    )


def test_read_tools_record_started_and_completed(scenario_factory):
    scenario = scenario_factory("F01")
    request = _start(scenario)
    customer_id = scenario.seeded.customer["customer_id"]
    result = scenario.tools.lookup_customer(
        customer_id,
        intent_id=request.intent_id,
        tool_call_id=tool_call_id(scenario.case_id, 0),
    )
    assert result["ok"] and result["customer"]["customer_id"] == customer_id
    assert [event.event_type for event in scenario.ledger.events()] == [
        EventType.USER_INTENT,
        EventType.TOOL_CALL_STARTED,
        EventType.TOOL_CALL_COMPLETED,
    ]
    assert scenario.ledger.verify_chain() == (True, None)


def test_killer_timeout_after_commit_unsafe_retry_is_47_then_94(scenario_factory):
    scenario = scenario_factory("F02", 0)
    request = _start(scenario)
    order = scenario.seeded.orders[0]
    assert order["amount_cents"] == 4700

    with pytest.raises(ToolTimeout, match="commit status is unknown"):
        _refund(scenario, request, 0)
    result = _refund(scenario, request, 1)

    assert result["requested_amount_cents"] == 4700
    assert scenario.db.snapshot_order(order["order_id"])["refunded_cents"] == 9400
    assert scenario.db.count_refunds(order["order_id"]) == 2
    commits = [event for event in scenario.ledger.events() if event.event_type == EventType.STATE_CHANGED]
    timeout = next(event for event in scenario.ledger.events() if event.event_type == EventType.NETWORK_TIMEOUT)
    assert len(commits) == 2 and commits[0].seq < timeout.seq < commits[1].seq
    assert commits[0].state_before["refunded_cents"] == 0
    assert commits[0].state_after["refunded_cents"] == 4700
    assert commits[1].state_before["refunded_cents"] == 4700
    assert commits[1].state_after["refunded_cents"] == 9400
    assert len({event.transaction_id for event in commits}) == 2
    assert scenario.ledger.verify_chain() == (True, None)

    refund_events = [event for event in scenario.ledger.events() if event.tool_name == "issue_refund"]
    assert all(event.payload["requested_order_id"] == order["order_id"] for event in refund_events)
    assert all(event.payload["requested_amount_cents"] == 4700 for event in refund_events)
    assert all(event.entity == f"order:{order['order_id']}" for event in commits)


def test_timeout_before_commit_then_retry_has_one_commit(scenario_factory):
    scenario = scenario_factory("F03", 0)
    request = _start(scenario)
    order = scenario.seeded.orders[0]
    with pytest.raises(ToolTimeout, match="commit status is unknown"):
        _refund(scenario, request, 0)
    assert scenario.db.snapshot_order(order["order_id"])["refunded_cents"] == 0

    _refund(scenario, request, 1)
    assert scenario.db.snapshot_order(order["order_id"])["refunded_cents"] == 4700
    commits = [event for event in scenario.ledger.events() if event.event_type == EventType.STATE_CHANGED]
    assert len(commits) == 1


def test_timeout_after_commit_safe_retry_is_idempotent(scenario_factory):
    scenario = scenario_factory("F10", 0)
    request = _start(scenario)
    order = scenario.seeded.orders[0]
    with pytest.raises(ToolTimeout):
        _refund(scenario, request, 0)
    replay = _refund(scenario, request, 1)

    assert replay["replayed"] is True
    assert scenario.db.snapshot_order(order["order_id"])["refunded_cents"] == 4700
    events = scenario.ledger.events()
    assert sum(event.event_type == EventType.STATE_CHANGED for event in events) == 1
    assert sum(event.event_type == EventType.IDEMPOTENT_REPLAY for event in events) == 1


def test_phantom_success_reports_success_without_commit(scenario_factory):
    scenario = scenario_factory("F04", 0)
    request = _start(scenario)
    result = _refund(scenario, request, 0)
    order_id = scenario.seeded.orders[0]["order_id"]
    assert result["ok"] and result["transaction_id"].startswith("txn_")
    assert "fault_kind" not in result
    assert scenario.db.snapshot_order(order_id)["refunded_cents"] == 0
    assert not any(event.event_type == EventType.STATE_CHANGED for event in scenario.ledger.events())


def test_amount_drift_records_actual_but_reports_requested(scenario_factory):
    scenario = scenario_factory("F05", 0)
    request = _start(scenario)
    result = _refund(scenario, request, 0)
    commit = next(event for event in scenario.ledger.events() if event.event_type == EventType.STATE_CHANGED)
    assert result["requested_amount_cents"] == 4700
    assert commit.payload["committed_amount_cents"] == 3700
    assert commit.state_after["refunded_cents"] == 3700


def test_partial_commit_records_half_but_reports_full(scenario_factory):
    scenario = scenario_factory("F08", 0)
    request = _start(scenario)
    result = _refund(scenario, request, 0)
    commit = next(event for event in scenario.ledger.events() if event.event_type == EventType.STATE_CHANGED)
    assert result["requested_amount_cents"] == 4700
    assert commit.payload["committed_amount_cents"] == 2350
    assert commit.state_after["status"] == "partially_refunded"


def test_misrouted_write_changes_the_other_order(scenario_factory):
    scenario = scenario_factory("F06", 0)
    request = _start(scenario)
    requested, other = scenario.seeded.orders
    result = _refund(scenario, request, 0)
    commit = next(event for event in scenario.ledger.events() if event.event_type == EventType.STATE_CHANGED)

    assert result["requested_order_id"] == requested["order_id"]
    assert commit.entity == f"order:{other['order_id']}"
    assert commit.payload["committed_order_id"] == other["order_id"]
    assert scenario.db.snapshot_order(requested["order_id"])["refunded_cents"] == 0
    assert scenario.db.snapshot_order(other["order_id"])["refunded_cents"] == requested["amount_cents"]


def test_two_intents_do_not_share_idempotency_key(scenario_factory):
    scenario = scenario_factory("F07", 0)
    first = _start(scenario, 0)
    second = _start(scenario, 1)
    _refund(scenario, first, 0, order_index=0)
    _refund(scenario, second, 1, order_index=1)
    commits = [event for event in scenario.ledger.events() if event.event_type == EventType.STATE_CHANGED]
    assert len(commits) == 2
    assert commits[0].intent_id != commits[1].intent_id
    assert commits[0].idempotency_key != commits[1].idempotency_key


def test_send_email_is_intentionally_not_ledgered(scenario_factory):
    scenario = scenario_factory("F09", 0)
    request = _start(scenario)
    before = len(scenario.ledger.events())
    result = scenario.tools.send_email(
        scenario.seeded.customer["email"],
        "Refund confirmation",
        "Done",
        intent_id=request.intent_id,
        tool_call_id=tool_call_id(scenario.case_id, 0),
    )
    assert result["ok"] and len(scenario.tools.sent_emails) == 1
    assert len(scenario.ledger.events()) == before


def test_reused_explicit_key_with_different_args_is_rejected(scenario_factory):
    scenario = scenario_factory("F01", 0)
    request = _start(scenario)
    key = "idem_explicit"
    _refund(scenario, request, 0, key=key)
    order_id = scenario.seeded.orders[0]["order_id"]
    with pytest.raises(IdempotencyConflict):
        scenario.tools.issue_refund(
            order_id,
            100,
            intent_id=request.intent_id,
            tool_call_id=tool_call_id(scenario.case_id, 1),
            idempotency_key=key,
        )
    assert scenario.db.count_refunds(order_id) == 1
    assert scenario.ledger.events()[-1].event_type == EventType.TOOL_CALL_FAILED


def test_business_commit_rolls_back_if_state_changed_cannot_be_ledgered(
    scenario_factory, monkeypatch
):
    scenario = scenario_factory("F01", 0)
    request = _start(scenario)
    order_id = scenario.seeded.orders[0]["order_id"]
    original_append = scenario.ledger.append

    def fail_state_changed(event_type, **fields):
        if event_type == EventType.STATE_CHANGED:
            raise RuntimeError("simulated ledger write failure")
        return original_append(event_type, **fields)

    monkeypatch.setattr(scenario.ledger, "append", fail_state_changed)
    with pytest.raises(RuntimeError, match="ledger write failure"):
        _refund(scenario, request, 0)

    assert scenario.db.snapshot_order(order_id)["refunded_cents"] == 0
    assert scenario.db.count_refunds(order_id) == 0
    assert scenario.ledger.events()[-1].event_type == EventType.TOOL_CALL_FAILED
