"""Append-only, hash-chained event ledger backed by the SQLite ``ledger`` table.

The ledger records what *actually happened*. The agent never writes to it and
never reads it directly; tools write to it as a side effect of running. The
auditors later receive the full list of events as raw JSON - the same list for
the baseline and for ProofTrail.
"""
from __future__ import annotations

import json
from typing import Any

from ..ids import transaction_id as make_transaction_id
from ..schemas.events import GENESIS_HASH, EventType, LedgerEvent, verify_chain
from .clock import SimClock
from .database import StateDB


class Ledger:
    def __init__(self, db: StateDB, clock: SimClock, case_id: str):
        self.db = db
        self.clock = clock
        self.case_id = case_id

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def append(self, event_type: str, **fields: Any) -> LedgerEvent:
        """Append one event. Assigns seq, ts, prev_hash and hash."""
        last = self.db.ledger_last_row()
        seq = (last["seq"] + 1) if last else 1
        prev_hash = last["hash"] if last else GENESIS_HASH
        event = LedgerEvent(seq=seq, ts=self.clock.tick(), event_type=event_type, **fields).seal(prev_hash)
        self.db.ledger_insert(self._to_row(event))
        return event

    def next_transaction_id(self) -> str:
        """Transaction ids are bound to the ledger position they will occupy."""
        last = self.db.ledger_last_row()
        seq = (last["seq"] + 1) if last else 1
        return make_transaction_id(self.case_id, seq)

    # Convenience writers used by tools --------------------------------- #
    def user_intent(self, intent_id: str, text: str) -> LedgerEvent:
        return self.append(EventType.USER_INTENT, intent_id=intent_id, payload={"text": text})

    def note(self, text: str, **payload: Any) -> LedgerEvent:
        return self.append(EventType.NOTE, payload={"text": text, **payload})

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def events(self) -> list[LedgerEvent]:
        return [self._from_row(r) for r in self.db.ledger_rows()]

    def last(self) -> LedgerEvent | None:
        row = self.db.ledger_last_row()
        return self._from_row(row) if row else None

    def verify_chain(self) -> tuple[bool, int | None]:
        return verify_chain(self.events())

    def to_json(self) -> str:
        return json.dumps([e.to_dict() for e in self.events()], indent=2, sort_keys=True)

    # ------------------------------------------------------------------ #
    # Row mapping
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_row(e: LedgerEvent) -> dict[str, Any]:
        return {
            "seq": e.seq,
            "ts": e.ts,
            "event_type": e.event_type,
            "tool_name": e.tool_name,
            "intent_id": e.intent_id,
            "tool_call_id": e.tool_call_id,
            "transaction_id": e.transaction_id,
            "idempotency_key": e.idempotency_key,
            "entity": e.entity,
            "state_before": json.dumps(e.state_before, sort_keys=True) if e.state_before is not None else None,
            "state_after": json.dumps(e.state_after, sort_keys=True) if e.state_after is not None else None,
            "payload": json.dumps(e.payload, sort_keys=True),
            "prev_hash": e.prev_hash,
            "hash": e.hash,
        }

    @staticmethod
    def _from_row(r: Any) -> LedgerEvent:
        return LedgerEvent(
            seq=r["seq"],
            ts=r["ts"],
            event_type=r["event_type"],
            tool_name=r["tool_name"],
            intent_id=r["intent_id"],
            tool_call_id=r["tool_call_id"],
            transaction_id=r["transaction_id"],
            idempotency_key=r["idempotency_key"],
            entity=r["entity"],
            state_before=json.loads(r["state_before"]) if r["state_before"] is not None else None,
            state_after=json.loads(r["state_after"]) if r["state_after"] is not None else None,
            payload=json.loads(r["payload"]),
            prev_hash=r["prev_hash"],
            hash=r["hash"],
        )
