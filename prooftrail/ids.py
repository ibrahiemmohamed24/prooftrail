"""Deterministic identifiers for intents, tool calls, transactions and idempotency.

Why four different ids (from the design review):

* ``intent_id``       — one per *user request*. Two refunds under the same
  intent are a retry; two refunds under different intents may both be legitimate.
* ``tool_call_id``    — one per attempt. A retry has a new tool_call_id but the
  same intent_id.
* ``transaction_id``  — one per *committed* state change. Assigned by the
  environment, never by the agent.
* ``idempotency_key`` — derived from (intent_id, tool, canonical args). A retry of
  the same intent with the same args produces the SAME key, which is what lets
  an idempotent tool return the original transaction instead of committing twice.

All ids are derived by hashing so that frozen cases are reproducible bit-for-bit.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(*parts: Any, length: int = 12) -> str:
    material = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:length]


def canonical_args(args: dict[str, Any]) -> str:
    """Stable JSON for a tool's arguments (key order + whitespace independent)."""
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)


def intent_id(case_id: str, ordinal: int) -> str:
    """The ``ordinal``-th distinct user request in a case (0-based)."""
    return f"int_{_digest('intent', case_id, ordinal)}"


def tool_call_id(case_id: str, attempt_ordinal: int) -> str:
    """The ``attempt_ordinal``-th tool call attempt in a case (0-based)."""
    return f"tc_{_digest('tool_call', case_id, attempt_ordinal)}"


def transaction_id(case_id: str, ledger_seq: int) -> str:
    """Assigned by the environment when a state change is committed."""
    return f"txn_{_digest('txn', case_id, ledger_seq)}"


def idempotency_key(intent: str, tool_name: str, args: dict[str, Any]) -> str:
    """Same intent + same tool + same args  ->  same key (that's the point)."""
    return f"idem_{_digest('idem', intent, tool_name, canonical_args(args), length=16)}"


def case_id(family_id: str, seed: int) -> str:
    return f"{family_id}-s{seed:02d}"


def entity_ref(kind: str, key: str) -> str:
    """Uniform entity reference used in ledger events, e.g. ``order:ord_1a2b``."""
    return f"{kind}:{key}"
