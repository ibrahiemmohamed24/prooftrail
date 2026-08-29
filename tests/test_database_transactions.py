def test_apply_refund_joins_callers_transaction(db):
    db.begin()
    after = db.apply_refund(
        refund_id="rf_nested",
        order_id="ord_1",
        amount_cents=4700,
        transaction_id="txn_nested",
        intent_id="int_nested",
        idempotency_key="idem_nested",
        tool_call_id="tc_nested",
        created_ts="2026-08-28T09:00:00+00:00",
    )
    assert after["refunded_cents"] == 4700
    assert db.conn.in_transaction

    db.rollback()
    assert db.snapshot_order("ord_1")["refunded_cents"] == 0
    assert db.get_refund_by_transaction("txn_nested") is None
