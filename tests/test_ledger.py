import sqlite3

import pytest

from prooftrail.schemas import GENESIS_HASH, EventType, LedgerEvent
from prooftrail.schemas.events import verify_chain


def test_append_assigns_seq_ts_and_chain(ledger):
    e1 = ledger.user_intent("int_a", "refund please")
    e2 = ledger.append(EventType.TOOL_CALL_STARTED, tool_name="lookup_order", intent_id="int_a", tool_call_id="tc_1")
    assert (e1.seq, e2.seq) == (1, 2)
    assert e1.prev_hash == GENESIS_HASH
    assert e2.prev_hash == e1.hash
    assert e1.ts < e2.ts, "simulated clock must advance"
    assert len(e1.hash) == 64


def test_roundtrip_through_sqlite_preserves_hashes(ledger):
    ledger.user_intent("int_a", "x")
    ledger.append(
        EventType.STATE_CHANGED,
        tool_name="issue_refund",
        intent_id="int_a",
        tool_call_id="tc_1",
        transaction_id="txn_1",
        idempotency_key="idem_1",
        entity="order:ord_1",
        state_before={"refunded_cents": 0, "status": "paid"},
        state_after={"refunded_cents": 8400, "status": "refunded"},
        payload={"amount_cents": 8400},
    )
    events = ledger.events()
    assert [e.seq for e in events] == [1, 2]
    assert events[1].state_after == {"refunded_cents": 8400, "status": "refunded"}
    assert events[1].is_commit
    ok, bad = ledger.verify_chain()
    assert ok and bad is None


def test_tamper_detection_on_frozen_list(ledger):
    ledger.user_intent("int_a", "x")
    ledger.note("hello")
    ledger.note("world")
    events = ledger.events()
    events[1].payload["text"] = "tampered"
    ok, bad = verify_chain(events)
    assert not ok and bad == 2


def test_missing_event_breaks_chain(ledger):
    for i in range(3):
        ledger.note(f"n{i}")
    events = ledger.events()
    del events[1]
    ok, bad = verify_chain(events)
    assert not ok and bad == 3


def test_ledger_table_is_append_only(ledger, db):
    ledger.note("immutable")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.conn.execute("UPDATE ledger SET payload='{}' WHERE seq=1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        db.conn.execute("DELETE FROM ledger WHERE seq=1")
    assert len(ledger.events()) == 1


def test_next_transaction_id_is_bound_to_position(ledger):
    t1 = ledger.next_transaction_id()
    ledger.note("occupies seq 1")
    t2 = ledger.next_transaction_id()
    assert t1 != t2
    assert ledger.next_transaction_id() == t2  # id for seq 2 stays stable until used


def test_unknown_event_type_rejected():
    with pytest.raises(ValueError):
        LedgerEvent(seq=1, ts="t", event_type="made_up")


def test_to_json_is_sorted_and_complete(ledger):
    ledger.user_intent("int_a", "x")
    js = ledger.to_json()
    assert '"event_type": "user_intent"' in js
    assert '"prev_hash"' in js
