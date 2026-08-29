from prooftrail.agent import RefundAgent, ScriptedModelClient, ToolSpec, ToolSuiteAction
from prooftrail.env import FaultInjector, FaultKind, FaultSpec, Ledger, RefundTool, SimClock, StateDB
from prooftrail.ids import intent_id


ISSUE_REFUND_SPEC = ToolSpec(
    "issue_refund",
    "Issue a refund in integer cents.",
    {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "amount_cents": {"type": "integer"},
        },
        "required": ["order_id", "amount_cents"],
    },
)


def test_dispatch_adapter_connects_agent_to_stateful_killer_environment():
    db = StateDB(":memory:").init_schema()
    try:
        db.insert_customer("cus_47", "Demo User", "demo@example.com")
        db.insert_order("ord_47", "cus_47", 4700, "2026-08-28T09:00:00+00:00")
        ledger = Ledger(db, SimClock(), case_id="F02-s00")
        suite = RefundTool(
            db,
            ledger,
            FaultInjector(
                [FaultSpec(FaultKind.TIMEOUT_AFTER_COMMIT, "issue_refund", nth_call=1)]
            ),
            idempotency_enabled=False,
        )
        action = ToolSuiteAction(
            suite,
            ISSUE_REFUND_SPEC,
            pass_idempotency_key=True,
            sequence_reader=lambda: ledger.last().seq if ledger.last() is not None else None,
        )
        request_intent = intent_id("F02-s00", 0)
        client = ScriptedModelClient.blind_refund_retry_demo(
            order_id="ord_47", intent_id=request_intent
        )

        trace = RefundAgent(client, [action]).run_request(
            case_id="F02-s00",
            intent_id=request_intent,
            text="Please refund $47.00 for order ord_47.",
        )

        assert db.snapshot_order("ord_47")["refunded_cents"] == 9400
        assert db.snapshot_order("ord_47")["refund_count"] == 2
        assert trace.final_report == "I refunded $47.00 for order ord_47."
        assert trace.tool_calls[0].error.startswith("ToolTimeout")
        assert trace.tool_calls[0].started_seq == 1
        assert trace.tool_calls[0].ended_seq == 3
        assert trace.tool_calls[1].started_seq == 4
        assert trace.tool_calls[1].ended_seq == 6
        assert ledger.verify_chain() == (True, None)
    finally:
        db.close()
