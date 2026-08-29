"""Small adapters between the agent protocol and dispatch-style tool suites."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .interfaces import ToolContext, ToolExecution, ToolSpec


class DispatchToolSuite(Protocol):
    """Protocol implemented by a suite that dispatches calls by tool name."""

    def call(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        intent_id: str,
        tool_call_id: str,
    ) -> Mapping[str, Any]:
        ...


@dataclass
class ToolSuiteAction:
    """Expose one action of a dispatch-style suite as an ``AgentTool``.

    ``sequence_reader`` should return the current last ledger sequence. When
    supplied, the adapter records the complete event range even if the suite
    raises a timeout after committing. ``pass_idempotency_key`` is normally
    true only for a mutating action such as ``issue_refund``.
    """

    suite: DispatchToolSuite
    spec: ToolSpec
    pass_idempotency_key: bool = False
    sequence_reader: Callable[[], int | None] | None = None

    def execute(
        self,
        arguments: Mapping[str, Any],
        context: ToolContext,
    ) -> ToolExecution:
        payload = {
            key: value
            for key, value in arguments.items()
            if key not in {"intent_id", "tool_call_id", "idempotency_key"}
        }
        if self.pass_idempotency_key:
            payload["idempotency_key"] = context.idempotency_key

        before_seq = self.sequence_reader() if self.sequence_reader is not None else None
        try:
            result = self.suite.call(
                self.spec.name,
                payload,
                intent_id=context.intent_id,
                tool_call_id=context.tool_call_id,
            )
        except Exception as exc:
            after_seq = self.sequence_reader() if self.sequence_reader is not None else None
            return ToolExecution.failure(
                f"{type(exc).__name__}: {exc}",
                started_seq=self._started_seq(before_seq, after_seq),
                ended_seq=after_seq,
            )

        after_seq = self.sequence_reader() if self.sequence_reader is not None else None
        return ToolExecution.success(
            result,
            started_seq=self._started_seq(before_seq, after_seq),
            ended_seq=after_seq,
        )

    @staticmethod
    def _started_seq(before_seq: int | None, after_seq: int | None) -> int | None:
        if after_seq is None:
            return None
        if before_seq is None:
            return 1 if after_seq >= 1 else None
        return before_seq + 1 if after_seq > before_seq else None
