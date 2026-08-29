"""SQLite business state: customers, orders, refunds - plus the ledger table.

Design rules
------------
* The ``ledger`` table is append-only. Two triggers abort any UPDATE or DELETE,
  so even a bug in this package cannot rewrite history.
* Every mutating method returns the *after* snapshot; callers are expected to
  take a ``snapshot_order`` *before* mutating so the ledger can carry both.
* Money is stored as integer cents to avoid float drift in reconciliation.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    customer_id     TEXT NOT NULL REFERENCES customers(customer_id),
    amount_cents    INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency        TEXT NOT NULL DEFAULT 'USD',
    status          TEXT NOT NULL CHECK (status IN ('paid','partially_refunded','refunded')),
    refunded_cents  INTEGER NOT NULL DEFAULT 0 CHECK (refunded_cents >= 0),
    created_ts      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id        TEXT PRIMARY KEY,
    order_id         TEXT NOT NULL REFERENCES orders(order_id),
    amount_cents     INTEGER NOT NULL CHECK (amount_cents > 0),
    transaction_id   TEXT NOT NULL UNIQUE,
    intent_id        TEXT NOT NULL,
    idempotency_key  TEXT NOT NULL,
    tool_call_id     TEXT NOT NULL,
    created_ts       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS refunds_by_order ON refunds(order_id);
CREATE INDEX IF NOT EXISTS refunds_by_idem  ON refunds(idempotency_key);

CREATE TABLE IF NOT EXISTS ledger (
    seq             INTEGER PRIMARY KEY,
    ts              TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    tool_name       TEXT,
    intent_id       TEXT,
    tool_call_id    TEXT,
    transaction_id  TEXT,
    idempotency_key TEXT,
    entity          TEXT,
    state_before    TEXT,
    state_after     TEXT,
    payload         TEXT NOT NULL DEFAULT '{}',
    prev_hash       TEXT NOT NULL,
    hash            TEXT NOT NULL UNIQUE
);

CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only: UPDATE forbidden');
END;

CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only: DELETE forbidden');
END;
"""


class StateDB:
    """Thin, explicit wrapper over sqlite3. No ORM - judges can read it."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, isolation_level=None)  # autocommit off via BEGIN
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def init_schema(self) -> "StateDB":
        self.conn.executescript(SCHEMA)
        return self

    def close(self) -> None:
        self.conn.close()

    def begin(self) -> None:
        self.conn.execute("BEGIN")

    def commit(self) -> None:
        self.conn.execute("COMMIT")

    def rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    # ------------------------------------------------------------------ #
    # Seeding
    # ------------------------------------------------------------------ #
    def insert_customer(self, customer_id: str, name: str, email: str) -> None:
        self.conn.execute(
            "INSERT INTO customers(customer_id, name, email) VALUES (?,?,?)",
            (customer_id, name, email),
        )

    def insert_order(
        self,
        order_id: str,
        customer_id: str,
        amount_cents: int,
        created_ts: str,
        currency: str = "USD",
        status: str = "paid",
        refunded_cents: int = 0,
    ) -> None:
        self.conn.execute(
            "INSERT INTO orders(order_id, customer_id, amount_cents, currency, status, refunded_cents, created_ts)"
            " VALUES (?,?,?,?,?,?,?)",
            (order_id, customer_id, amount_cents, currency, status, refunded_cents, created_ts),
        )

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
        return dict(row) if row else None

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def list_orders_for_customer(self, customer_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE customer_id=? ORDER BY created_ts, order_id", (customer_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def snapshot_order(self, order_id: str) -> dict[str, Any] | None:
        """The exact dict that goes into ``state_before`` / ``state_after``."""
        o = self.get_order(order_id)
        if o is None:
            return None
        return {
            "order_id": o["order_id"],
            "status": o["status"],
            "amount_cents": o["amount_cents"],
            "refunded_cents": o["refunded_cents"],
            "refund_count": self.count_refunds(order_id),
        }

    def list_refunds(self, order_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM refunds WHERE order_id=? ORDER BY created_ts, refund_id", (order_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def count_refunds(self, order_id: str) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM refunds WHERE order_id=?", (order_id,)).fetchone()[0]

    def find_refund_by_idempotency_key(self, key: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM refunds WHERE idempotency_key=?", (key,)).fetchone()
        return dict(row) if row else None

    def get_refund_by_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM refunds WHERE transaction_id=?", (transaction_id,)).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ #
    # The one mutation that matters
    # ------------------------------------------------------------------ #
    def apply_refund(
        self,
        *,
        refund_id: str,
        order_id: str,
        amount_cents: int,
        transaction_id: str,
        intent_id: str,
        idempotency_key: str,
        tool_call_id: str,
        created_ts: str,
    ) -> dict[str, Any]:
        """Commit a refund. Deliberately does NOT enforce 'not over-refunded':
        the environment must be able to represent the double-refund bug, and
        the ledger must be able to prove it happened.

        If the caller already opened a transaction, this method joins it and
        leaves commit/rollback to that caller.  ``RefundTools`` uses that path
        to insert the matching STATE_CHANGED ledger row in the *same* SQLite
        transaction as the business mutation.  Direct callers retain the old
        all-or-nothing behaviour.
        """
        order = self.get_order(order_id)
        if order is None:
            raise KeyError(f"order {order_id} not found")
        owns_transaction = not self.conn.in_transaction
        if owns_transaction:
            self.begin()
        try:
            self.conn.execute(
                "INSERT INTO refunds(refund_id, order_id, amount_cents, transaction_id, intent_id,"
                " idempotency_key, tool_call_id, created_ts) VALUES (?,?,?,?,?,?,?,?)",
                (refund_id, order_id, amount_cents, transaction_id, intent_id, idempotency_key, tool_call_id, created_ts),
            )
            new_refunded = order["refunded_cents"] + amount_cents
            status = "refunded" if new_refunded >= order["amount_cents"] else "partially_refunded"
            self.conn.execute(
                "UPDATE orders SET refunded_cents=?, status=? WHERE order_id=?",
                (new_refunded, status, order_id),
            )
            after = self.snapshot_order(order_id) or {}
            if owns_transaction:
                self.commit()
        except Exception:
            if owns_transaction and self.conn.in_transaction:
                self.rollback()
            raise
        return after

    # ------------------------------------------------------------------ #
    # Ledger table access (used only by Ledger)
    # ------------------------------------------------------------------ #
    def ledger_last_row(self) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()

    def ledger_rows(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM ledger ORDER BY seq").fetchall()

    def ledger_insert(self, row: dict[str, Any]) -> None:
        cols = ",".join(row.keys())
        marks = ",".join("?" for _ in row)
        self.conn.execute(f"INSERT INTO ledger({cols}) VALUES ({marks})", tuple(row.values()))
