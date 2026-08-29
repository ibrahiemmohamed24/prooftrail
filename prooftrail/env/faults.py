"""Fault injection: the environment misbehaves, the agent reports what it saw.

We audit a *real* LLM agent, so we cannot script it to lie. Instead the tools
lie to it, time out on it, or write somewhere else - exactly the failure modes
that happen in production payment integrations. The agent then honestly
reports what the tool told it, and that report may contradict the ledger.

Each kind is applied by ``env.tools`` at a specific point in ``issue_refund``:

TIMEOUT_AFTER_COMMIT   commit the refund, write STATE_CHANGED, *then* raise
                       ToolTimeout to the agent. The killer scenario. Whether
                       a retry double-refunds depends on ``idempotency_enabled``.
TIMEOUT_BEFORE_COMMIT  raise ToolTimeout before touching state. A retry is
                       legitimate and yields exactly one refund.
PHANTOM_SUCCESS        return a success payload with a fake transaction id but
                       commit nothing. No STATE_CHANGED event exists.
AMOUNT_DRIFT           commit ``amount + delta_cents`` but report ``amount``.
MISROUTED_WRITE        commit to the customer's *other* order, report the
                       requested one.
PARTIAL_COMMIT         commit ``round(amount * fraction)`` but report ``amount``.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


class FaultKind:
    TIMEOUT_AFTER_COMMIT = "timeout_after_commit"
    TIMEOUT_BEFORE_COMMIT = "timeout_before_commit"
    PHANTOM_SUCCESS = "phantom_success"
    AMOUNT_DRIFT = "amount_drift"
    MISROUTED_WRITE = "misrouted_write"
    PARTIAL_COMMIT = "partial_commit"

    ALL = (
        TIMEOUT_AFTER_COMMIT,
        TIMEOUT_BEFORE_COMMIT,
        PHANTOM_SUCCESS,
        AMOUNT_DRIFT,
        MISROUTED_WRITE,
        PARTIAL_COMMIT,
    )


class ToolTimeout(Exception):
    """What the agent sees: the call did not return. It learns nothing about
    whether the operation committed - that is the whole point."""


@dataclass(frozen=True)
class FaultSpec:
    kind: str
    tool: str                       # tool name it applies to, e.g. "issue_refund"
    nth_call: int = 1               # fire on the N-th call *of that tool* (1-based)
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in FaultKind.ALL:
            raise ValueError(f"unknown fault kind {self.kind!r}")
        if self.nth_call < 1:
            raise ValueError("nth_call is 1-based")


@dataclass
class FiredFault:
    spec: FaultSpec
    tool_call_id: str
    call_index: int


class FaultInjector:
    """Decides, per tool call, whether a fault fires. Records what fired so the
    ground-truth builder can point at the exact call (independent of the LLM)."""

    def __init__(self, specs: list[FaultSpec] | None = None):
        self.specs = list(specs or [])
        self._calls: dict[str, int] = defaultdict(int)
        self.fired: list[FiredFault] = []

    def record_call(self, tool: str) -> int:
        """Increment and return the 1-based call index for ``tool``."""
        self._calls[tool] += 1
        return self._calls[tool]

    def active(self, tool: str, call_index: int, tool_call_id: str) -> FaultSpec | None:
        """Return the fault that fires for this call (at most one), and log it."""
        for spec in self.specs:
            if spec.tool == tool and spec.nth_call == call_index:
                self.fired.append(FiredFault(spec, tool_call_id, call_index))
                return spec
        return None

    def calls_so_far(self, tool: str) -> int:
        return self._calls[tool]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {"kind": f.spec.kind, "tool": f.spec.tool, "nth_call": f.spec.nth_call,
             "tool_call_id": f.tool_call_id, "params": dict(f.spec.params)}
            for f in self.fired
        ]
