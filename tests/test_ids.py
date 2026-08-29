from prooftrail import ids


def test_ids_are_deterministic():
    assert ids.intent_id("F02-s00", 0) == ids.intent_id("F02-s00", 0)
    assert ids.tool_call_id("F02-s00", 3) == ids.tool_call_id("F02-s00", 3)
    assert ids.transaction_id("F02-s00", 7) == ids.transaction_id("F02-s00", 7)


def test_ids_differ_across_cases_and_ordinals():
    assert ids.intent_id("F02-s00", 0) != ids.intent_id("F02-s01", 0)
    assert ids.intent_id("F02-s00", 0) != ids.intent_id("F02-s00", 1)
    assert ids.tool_call_id("F02-s00", 0) != ids.tool_call_id("F02-s00", 1)


def test_prefixes():
    assert ids.intent_id("c", 0).startswith("int_")
    assert ids.tool_call_id("c", 0).startswith("tc_")
    assert ids.transaction_id("c", 1).startswith("txn_")
    assert ids.idempotency_key("int_x", "issue_refund", {}).startswith("idem_")
    assert ids.case_id("F02", 3) == "F02-s03"
    assert ids.entity_ref("order", "ord_1") == "order:ord_1"


def test_retry_same_intent_same_args_same_key():
    """A retry of the same user intent must produce the SAME idempotency key."""
    intent = ids.intent_id("F02-s00", 0)
    k1 = ids.idempotency_key(intent, "issue_refund", {"order_id": "ord_1", "amount_cents": 8400})
    k2 = ids.idempotency_key(intent, "issue_refund", {"amount_cents": 8400, "order_id": "ord_1"})
    assert k1 == k2, "key must be independent of argument order"


def test_new_intent_new_key():
    """Two legitimate refund requests (different intents) must NOT collide."""
    a = ids.intent_id("F07-s00", 0)
    b = ids.intent_id("F07-s00", 1)
    args = {"order_id": "ord_1", "amount_cents": 8400}
    assert ids.idempotency_key(a, "issue_refund", args) != ids.idempotency_key(b, "issue_refund", args)


def test_different_args_different_key():
    intent = ids.intent_id("F05-s00", 0)
    assert ids.idempotency_key(intent, "issue_refund", {"amount_cents": 1}) != ids.idempotency_key(
        intent, "issue_refund", {"amount_cents": 2}
    )
