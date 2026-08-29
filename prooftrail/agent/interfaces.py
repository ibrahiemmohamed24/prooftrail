"""Provider-neutral contracts for the refund agent loop.

The agent deliberately depends on these small protocols instead of a concrete
LLM SDK or the mock refund environment. A live provider adapter and the
event-ledger-backed ``RefundTool`` can therefore be connected later without
changing the loop or the trace format.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..schemas import Usage


@dataclass(frozen=True)
class UserRequest:
    """One user intent handled by the agent."""

    intent_id: str
    text: str

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent_id must not be empty")
        if not self.text.strip():
            raise ValueError("request text must not be empty")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ToolSpec:
    """The model-facing description of one callable tool."""

    name: str
    description: str
    input_schema: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolCall:
    """A tool request emitted by a model client.

    ``provider_call_id`` is retained only for provider adapters. ProofTrail's
    own deterministic ``tool_call_id`` is assigned by :class:`RefundAgent`.
    """

    name: str
    arguments: dict[str, Any]
    provider_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ToolCall":
        return cls(
            name=str(raw["name"]),
            arguments=dict(raw.get("arguments", {})),
            provider_call_id=raw.get("provider_call_id"),
        )


@dataclass(frozen=True)
class ModelResponse:
    """One provider-neutral assistant turn."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
            "usage": self.usage.to_dict(),
            "stop_reason": self.stop_reason,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ModelResponse":
        return cls(
            text=str(raw.get("text", "")),
            tool_calls=tuple(ToolCall.from_dict(c) for c in raw.get("tool_calls", [])),
            usage=Usage(**dict(raw.get("usage", {}))),
            stop_reason=raw.get("stop_reason"),
        )


@runtime_checkable
class ModelClient(Protocol):
    """Minimal interface implemented by live and scripted model adapters."""

    model_name: str
    is_live_model: bool

    def complete(
        self,
        *,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[ToolSpec],
        max_output_tokens: int,
        effort: str,
    ) -> ModelResponse:
        ...


@dataclass(frozen=True)
class ToolContext:
    """Correlation metadata owned by the runner, never trusted to the model."""

    case_id: str
    intent_id: str
    tool_call_id: str
    idempotency_key: str
    attempt_ordinal: int


@dataclass(frozen=True)
class ToolExecution:
    """Normalized result returned by an :class:`AgentTool`.

    A timeout-after-commit is represented with ``error`` set while
    ``started_seq``/``ended_seq`` still point at the ledger events. This keeps
    the trace complete without requiring the loop to know environment-specific
    exception types.
    """

    result: dict[str, Any] | None = None
    error: str | None = None
    started_seq: int | None = None
    ended_seq: int | None = None

    def __post_init__(self) -> None:
        if self.result is not None and self.error is not None:
            raise ValueError("a tool execution cannot contain both result and error")

    @classmethod
    def success(
        cls,
        result: Mapping[str, Any] | None = None,
        *,
        started_seq: int | None = None,
        ended_seq: int | None = None,
    ) -> "ToolExecution":
        return cls(dict(result or {}), None, started_seq, ended_seq)

    @classmethod
    def failure(
        cls,
        error: str,
        *,
        started_seq: int | None = None,
        ended_seq: int | None = None,
    ) -> "ToolExecution":
        return cls(None, error, started_seq, ended_seq)


@runtime_checkable
class AgentTool(Protocol):
    """A tool usable by :class:`RefundAgent`.

    ``arguments`` includes ``intent_id``, ``idempotency_key`` and
    ``tool_call_id`` injected by the runner. The same values are also present
    in ``context`` for adapters that prefer explicit metadata.
    """

    spec: ToolSpec

    def execute(
        self,
        arguments: Mapping[str, Any],
        context: ToolContext,
    ) -> ToolExecution | Mapping[str, Any]:
        ...
