"""Plain-dataclass schemas shared by the environment, the agent, every auditor
and the evaluator. Stdlib only (no pydantic) so replay mode has zero deps.

* ``events``  - one row of the append-only ledger
* ``trace``   - what the refund agent saw and did (frozen per case)
* ``verdict`` - the ONE output schema every auditor must emit, plus ground truth
"""
from .events import GENESIS_HASH, EventType, LedgerEvent
from .trace import AgentTrace, FrozenCase, ToolCallRecord, Usage
from .verdict import (
    STATUSES,
    AuditOutput,
    ClaimType,
    ClaimVerdict,
    GroundTruth,
    Status,
    aggregate_verdict,
    validate_audit_output,
)

__all__ = [
    "GENESIS_HASH",
    "EventType",
    "LedgerEvent",
    "AgentTrace",
    "FrozenCase",
    "ToolCallRecord",
    "Usage",
    "STATUSES",
    "AuditOutput",
    "ClaimType",
    "ClaimVerdict",
    "GroundTruth",
    "Status",
    "aggregate_verdict",
    "validate_audit_output",
]
