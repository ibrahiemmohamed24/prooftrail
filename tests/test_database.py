import pytest


def test_schema_and_seed(db):
    assert db.get_customer("cus_a")["name"] == "Amina Hassan"
    o = db.get_order("ord_1")
    assert o["amount_cents"] == 8400 and o["status"] == "paid" and o["refunded_cents"] == 0
    assert [o["order_id"] for o in db.list_orders_for_customer("cus_a")] == ["ord_1", "ord_2"]
    assert db.get_order("nope") is None


def test_snapshot_shape(db):
    snap = db.snapshot_order("ord_1")
    assert snap == {
        "order_id": "ord_1",
        "status": "paid",
        "amount_cents": 8400,
        "refunded_cents": 0,
        "refund_count": 0,
    }
    assert db.snapshot_order("nope") is None


def _refund(db, order_id="ord_1", amount=8400, n=1):
    return db.apply_refund(
        refund_id=f"rf_{n}",
        order_id=order_id,
        amount_cents=amount,
        transaction_id=f"txn_{n}",
        intent_id="int_a",
        idempotency_key=f"idem_{n}",
        tool_call_id=f"tc_{n}",
        created_ts="2026-08-28T09:00:07+00:00",
    )


def test_full_refund_updates_status(db):
    after = _refund(db)
    assert after["status"] == "refunded"
    assert after["refunded_cents"] == 8400
    assert after["refund_count"] == 1
    assert db.list_refunds("ord_1")[0]["transaction_id"] == "txn_1"


def test_partial_refund_status(db):
    after = _refund(db, amount=4200)
    assert after["status"] == "partially_refunded"
    assert after["refunded_cents"] == 4200


def test_double_refund_is_representable(db):
    """The environment must be able to record the bug we want to catch."""
    _refund(db, n=1)
    after = _refund(db, n=2)
    assert after["refund_count"] == 2
    assert after["refunded_cents"] == 16800  # over-refunded, and the state says so


def test_idempotency_lookup(db):
    _refund(db, n=1)
    assert db.find_refund_by_idempotency_key("idem_1")["transaction_id"] == "txn_1"
    assert db.find_refund_by_idempotency_key("idem_missing") is None
    assert db.get_refund_by_transaction("txn_1")["order_id"] == "ord_1"


def test_refund_unknown_order_raises_and_leaves_no_row(db):
    with pytest.raises(KeyError):
        _refund(db, order_id="ord_missing")
    assert db.conn.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 0


def test_duplicate_transaction_id_rolls_back(db):
    _refund(db, n=1)
    with pytest.raises(Exception):
        db.apply_refund(
            refund_id="rf_dup",
            order_id="ord_1",
            amount_cents=100,
            transaction_id="txn_1",  # UNIQUE violation
            intent_id="int_a",
            idempotency_key="idem_x",
            tool_call_id="tc_x",
            created_ts="t",
        )
    # order untouched by the failed attempt
    assert db.get_order("ord_1")["refunded_cents"] == 8400
