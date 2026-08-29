"""One row of the append-only event ledger.

The ledger is the *only* source of truth. Every tool call the agent makes
produces at least a STARTED and a COMPLETED/FAILED/TIMEOUT event; every
committed state change produces a STATE_CHANGED event with a full before/after
snapshot of the affected entity. Rows are hash-chained so tampering (or an
accidental mutation) is detectable by ``verify_chain()``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any


class EventType:
    USER_INTENT = "user_intent"                  # a new user request entered the system
    TOOL_CALL_STARTED = "tool_call_started"
    STATE_CHANGED = "state_changed"              # a commit happened (the only "truth" rows)
    TOOL_CALL_COMPLETED = "tool_call_completed"  # what the tool returned to the agent
    TOOL_CALL_FAILED = "tool_call_failed"        # env raised an error to the agent
    NETWORK_TIMEOUT = "network_timeout"          # agent saw a timeout (fault injected)
    IDEMPOTENT_REPLAY = "idempotent_replay"      # tool returned an existing txn, no commit
    NOTE = "note"                                # environment annotation, never agent-authored

    ALL = (
        USER_INTENT,
        TOOL_CALL_STARTED,
        STATE_CHANGED,
        TOOL_CALL_COMPLETED,
        TOOL_CALL_FAILED,
        NETWORK_TIMEOUT,
        IDEMPOTENT_REPLAY,
        NOTE,
    )


GENESIS_HASH = "0" * 64


@dataclass
class LedgerEvent:
    seq: int
    ts: str
    event_type: str
    tool_name: str | None = None
    intent_id: str | None = None
    tool_call_id: str | None = None
    transaction_id: str | None = None
    idempotency_key: str | None = None
    entity: str | None = None                    # e.g. "order:ord_1a2b"
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = GENESIS_HASH
    hash: str = ""

    def __post_init__(self) -> None:
        if self.event_type not in EventType.ALL:
            raise ValueError(f"unknown event_type {self.event_type!r}")

    # ------------------------------------------------------------------ #
    # Hash chain
    # ------------------------------------------------------------------ #
    def content_for_hash(self) -> str:
        d = asdict(self)
        d.pop("hash", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)

    def compute_hash(self) -> str:
        return hashlib.sha256(self.content_for_hash().encode("utf-8")).hexdigest()

    def seal(self, prev_hash: str) -> "LedgerEvent":
        self.prev_hash = prev_hash
        self.hash = self.compute_hash()
        return self

    # ------------------------------------------------------------------ #
    # (De)serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LedgerEvent":
        return cls(**d)

    # ------------------------------------------------------------------ #
    # Predicates used by the reconciler / metrics
    # ------------------------------------------------------------------ #
    @property
    def is_commit(self) -> bool:
        return self.event_type == EventType.STATE_CHANGED


def verify_chain(events: list[LedgerEvent]) -> tuple[bool, int | None]:
    """Return (ok, first_bad_seq). Works on a live ledger or a frozen list."""
    prev = GENESIS_HASH
    expected_seq = 1
    for e in events:
        if e.seq != expected_seq:
            return False, e.seq
        if e.prev_hash != prev or e.hash != e.compute_hash():
            return False, e.seq
        prev = e.hash
        expected_seq += 1
    return True, None
