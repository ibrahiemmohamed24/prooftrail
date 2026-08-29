"""The mock refund environment: SQLite state + append-only ledger + faults.

* ``clock``    - deterministic simulated time (reproducible timestamps/hashes)
* ``database`` - the business state the agent mutates (orders, refunds)
* ``ledger``   - the append-only, hash-chained event log = the only truth
* ``faults``   - fault injection that makes tools lie, time out, or misroute
* ``tools``    - the tool implementations the agent calls
* ``seed_data``- deterministic customers/orders per (family, seed)
"""
from .clock import SimClock
from .database import StateDB
from .faults import FaultInjector, FaultKind, FaultSpec, ToolTimeout
from .ledger import Ledger
from .seed_data import SeededEnvironment, format_usd, seed_environment
from .tools import IdempotencyConflict, RefundTool, RefundTools

__all__ = [
    "SimClock",
    "StateDB",
    "FaultInjector",
    "FaultKind",
    "FaultSpec",
    "ToolTimeout",
    "Ledger",
    "SeededEnvironment",
    "format_usd",
    "seed_environment",
    "IdempotencyConflict",
    "RefundTool",
    "RefundTools",
]
