"""What the refund agent saw and did. Frozen once, replayed forever.

A ``FrozenCase`` bundles the trace with the raw ledger so that a single JSON
file is *all* the evidence any auditor gets. Ground truth is stored in a
separate ``labels.json`` next to it and is never loaded by an auditor.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .events import LedgerEvent


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    llm_calls: int = 0

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            round(self.cost_usd + other.cost_usd, 6),
            self.llm_calls + other.llm_calls,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCallRecord:
    """One tool call *as the agent experienced it* (its view, not the ledger's)."""

    tool_call_id: str
    intent_id: str
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any] | None          # what the tool returned to the agent
    error: str | None                      # what the agent was told on failure
    started_seq: int | None                # ledger seq of TOOL_CALL_STARTED
    ended_seq: int | None                  # ledger seq of COMPLETED/FAILED/TIMEOUT


@dataclass
class AgentTrace:
    case_id: str
    model: str
    system_prompt_sha256: str
    user_requests: list[dict[str, Any]]    # [{intent_id, text}]
    messages: list[dict[str, Any]]         # full conversation as sent/received
    tool_calls: list[ToolCallRecord]
    final_report: str                      # the free-text claims we audit
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentTrace":
        d = dict(d)
        d["tool_calls"] = [ToolCallRecord(**tc) for tc in d.get("tool_calls", [])]
        d["usage"] = Usage(**d.get("usage", {}))
        return cls(**d)


@dataclass
class FrozenCase:
    """Everything an auditor is allowed to see. Nothing more."""

    case_id: str
    family_id: str
    seed: int
    trace: AgentTrace
    ledger: list[LedgerEvent]
    schema_version: int = 1

    def auditor_view(self) -> dict[str, Any]:
        """Return only task evidence, with benchmark metadata removed.

        ``family_id`` and ``seed`` are evaluator metadata, not evidence. The
        trace case id is removed too because its storage id encodes the family.
        Auditors still receive the same conversation, tool calls and ledger;
        the runner attaches the real case id to their output afterwards.
        """

        trace = self.trace.to_dict()
        trace.pop("case_id", None)
        return {
            "schema_version": self.schema_version,
            "trace": trace,
            "ledger": [event.to_dict() for event in self.ledger],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "family_id": self.family_id,
            "seed": self.seed,
            "trace": self.trace.to_dict(),
            "ledger": [e.to_dict() for e in self.ledger],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FrozenCase":
        return cls(
            case_id=d["case_id"],
            family_id=d["family_id"],
            seed=d["seed"],
            trace=AgentTrace.from_dict(d["trace"]),
            ledger=[LedgerEvent.from_dict(e) for e in d["ledger"]],
            schema_version=d.get("schema_version", 1),
        )
