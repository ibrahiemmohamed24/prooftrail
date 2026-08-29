"""Build an :class:`AgentTrace` while the refund agent runs."""
from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any, Mapping, Sequence

from ..schemas import AgentTrace, ToolCallRecord, Usage
from .interfaces import ModelResponse, ToolCall, ToolExecution, UserRequest


class AgentRecorder:
    """Mutable run-local recorder; :meth:`finish` returns an isolated snapshot."""

    def __init__(self, *, case_id: str, model_name: str, system_prompt: str):
        self.case_id = case_id
        self.model_name = model_name
        self.system_prompt_sha256 = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
        self.user_requests: list[dict[str, str]] = []
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        self.tool_calls: list[ToolCallRecord] = []
        self.usage = Usage()

    def model_messages(self) -> list[dict[str, Any]]:
        """Return a defensive copy suitable for passing to a model adapter."""
        return deepcopy(self.messages)

    def record_user(self, request: UserRequest) -> None:
        self.user_requests.append(request.to_dict())
        self.messages.append(
            {"role": "user", "intent_id": request.intent_id, "content": request.text}
        )

    def record_assistant(
        self,
        response: ModelResponse,
        assigned_calls: Sequence[tuple[str, ToolCall, Mapping[str, Any]]],
    ) -> None:
        message: dict[str, Any] = {"role": "assistant", "content": response.text}
        if assigned_calls:
            message["tool_calls"] = [
                {
                    "id": tool_call_id,
                    "provider_call_id": call.provider_call_id,
                    "name": call.name,
                    # Preserve what the model actually emitted. Correlation
                    # fields injected by the runner belong in ToolCallRecord,
                    # not in the assistant transcript.
                    "arguments": deepcopy(call.arguments),
                }
                for tool_call_id, call, _arguments in assigned_calls
            ]
        if response.raw_content:
            # Provider blocks (e.g. thinking + tool_use) are echoed back verbatim
            # on the next turn, so the frozen trace must carry them unchanged.
            message["provider_content"] = deepcopy(list(response.raw_content))
        if response.metadata:
            message["provider"] = deepcopy(response.metadata)
        self.messages.append(message)
        self.usage = self.usage.add(response.usage)

    def record_tool(
        self,
        *,
        tool_call_id: str,
        intent_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        execution: ToolExecution,
    ) -> None:
        result = deepcopy(execution.result)
        self.tool_calls.append(
            ToolCallRecord(
                tool_call_id=tool_call_id,
                intent_id=intent_id,
                tool_name=tool_name,
                args=deepcopy(dict(arguments)),
                result=result,
                error=execution.error,
                started_seq=execution.started_seq,
                ended_seq=execution.ended_seq,
            )
        )
        content: dict[str, Any]
        if execution.error is not None:
            content = {"error": execution.error}
        else:
            content = result or {}
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": tool_name,
                "content": content,
                "is_error": execution.error is not None,
            }
        )

    def finish(self, *, final_report: str, stop_reason: str | None) -> AgentTrace:
        return AgentTrace(
            case_id=self.case_id,
            model=self.model_name,
            system_prompt_sha256=self.system_prompt_sha256,
            user_requests=deepcopy(self.user_requests),
            messages=deepcopy(self.messages),
            tool_calls=deepcopy(self.tool_calls),
            final_report=final_report,
            usage=deepcopy(self.usage),
            stop_reason=stop_reason,
        )
